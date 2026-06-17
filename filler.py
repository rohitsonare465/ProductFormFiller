"""Safe typing engine for filling the currently focused browser form."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal
from pynput.keyboard import Controller, Key, KeyCode


FORBIDDEN_KEY_NAMES = {"enter", "return"}
FORBIDDEN_CHARACTERS = {"\r", "\n"}
FORBIDDEN_TEXT_CHARACTERS = {"\r", "\n", "\t"}


class FillStatus(str, Enum):
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


# pyrefly: ignore [unexpected-keyword]
@dataclass(frozen=True, slots=True)
class TypingDelays:
    character_min: float
    character_max: float
    word_pause_min: float
    word_pause_max: float
    tab_min: float
    tab_max: float
    field_pause_min: float
    field_pause_max: float
    group_fields_min: int
    group_fields_max: int
    group_pause_min: float
    group_pause_max: float
    long_description_pause_min: float
    long_description_pause_max: float
    jitter_ratio: float


SLOW_PROFILE = "slow"
NORMAL_PROFILE = "normal"
FAST_PROFILE = "fast"


# Fields that receive an extra "thinking" pause after typing.
LONG_TEXT_FIELDS = {"Long Description", "Legal Disclaimer"}


def timing_profile_to_delays(profile: str) -> TypingDelays:
    if profile == FAST_PROFILE:
        # Target: 2-3 minutes per 41-field form.
        return TypingDelays(
            character_min=0.02,
            character_max=0.05,
            word_pause_min=0.03,
            word_pause_max=0.08,
            tab_min=0.10,
            tab_max=0.25,
            field_pause_min=0.05,
            field_pause_max=0.15,
            group_fields_min=10,
            group_fields_max=15,
            group_pause_min=0.30,
            group_pause_max=0.80,
            long_description_pause_min=0.50,
            long_description_pause_max=1.20,
            jitter_ratio=0.0,
        )

    if profile == SLOW_PROFILE:
        # Target: 5-6 minutes per 41-field form.
        return TypingDelays(
            character_min=0.05,
            character_max=0.10,
            word_pause_min=0.10,
            word_pause_max=0.25,
            tab_min=0.30,
            tab_max=0.55,
            field_pause_min=0.25,
            field_pause_max=0.60,
            group_fields_min=5,
            group_fields_max=8,
            group_pause_min=1.00,
            group_pause_max=2.50,
            long_description_pause_min=2.00,
            long_description_pause_max=4.00,
            jitter_ratio=0.20,
        )

    # NORMAL_PROFILE — Target: 3-4 minutes per 41-field form.
    return TypingDelays(
        character_min=0.03,
        character_max=0.07,
        word_pause_min=0.05,
        word_pause_max=0.12,
        tab_min=0.15,
        tab_max=0.35,
        field_pause_min=0.10,
        field_pause_max=0.30,
        group_fields_min=8,
        group_fields_max=12,
        group_pause_min=0.50,
        group_pause_max=1.20,
        long_description_pause_min=1.00,
        long_description_pause_max=2.00,
        jitter_ratio=0.10,
    )


class FormFillerWorker(QObject):
    """Background worker that only types text and presses Tab between fields."""

    progress = pyqtSignal(int, int, str)
    field_started = pyqtSignal(int, str)
    paused_changed = pyqtSignal(bool)
    finished = pyqtSignal(str, str)

    def __init__(
        self,
        values: list[tuple[str, str, str]],
        delays: TypingDelays,
        startup_delay: float = 1.0,
    ) -> None:
        super().__init__()
        self._values = values
        self._delays = delays
        self._startup_delay = startup_delay
        self._keyboard = Controller()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._fields_until_pause = random.randint(
            self._delays.group_fields_min,
            self._delays.group_fields_max,
        )
        self._fields_since_pause = 0

    def pause(self) -> None:
        self._pause_event.clear()
        self.paused_changed.emit(True)

    def resume(self) -> None:
        self._pause_event.set()
        self.paused_changed.emit(False)

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()

    def run(self) -> None:
        try:
            if not self._sleep_interruptibly(self._startup_delay):
                self.finished.emit(FillStatus.STOPPED.value, "Stopped before typing.")
                return

            total = len(self._values)
            for index, (_csv_column, form_field, value) in enumerate(self._values):
                if self._should_stop():
                    self.finished.emit(FillStatus.STOPPED.value, "Stopped by user.")
                    return

                self.field_started.emit(index, form_field)
                self._type_text(value)
                self.progress.emit(index + 1, total, form_field)

                is_final_field = index == total - 1
                if not is_final_field:
                    self._pause_after_field(form_field)
                    self._wait_while_paused_or_stopped()
                    if self._should_stop():
                        self.finished.emit(FillStatus.STOPPED.value, "Stopped by user.")
                        return
                    self._press_tab()

            self.finished.emit(FillStatus.COMPLETED.value, "Finished Barcode field.")
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI.
            self.finished.emit(FillStatus.FAILED.value, str(exc))

    def _type_text(self, text: str) -> None:
        for character in text:
            self._wait_while_paused_or_stopped()
            if self._should_stop():
                return
            self._safe_type_character(character)
            self._sleep_interruptibly(self._delay(self._delays.character_min, self._delays.character_max))
            if character == " ":
                self._sleep_interruptibly(self._delay(self._delays.word_pause_min, self._delays.word_pause_max))

    def _press_tab(self) -> None:
        self._safe_press_key(Key.tab)
        self._safe_release_key(Key.tab)
        self._sleep_interruptibly(self._delay(self._delays.tab_min, self._delays.tab_max))

    def _pause_after_field(self, form_field: str) -> None:
        self._sleep_interruptibly(self._delay(self._delays.field_pause_min, self._delays.field_pause_max))
        if form_field in LONG_TEXT_FIELDS:
            self._sleep_interruptibly(
                self._delay(
                    self._delays.long_description_pause_min,
                    self._delays.long_description_pause_max,
                )
            )
        self._pause_after_field_group_if_needed()

    def _pause_after_field_group_if_needed(self) -> None:
        self._fields_since_pause += 1
        if self._fields_since_pause < self._fields_until_pause:
            return

        self._fields_since_pause = 0
        self._fields_until_pause = random.randint(
            self._delays.group_fields_min,
            self._delays.group_fields_max,
        )
        self._sleep_interruptibly(
            self._delay(self._delays.group_pause_min, self._delays.group_pause_max)
        )

    def _delay(self, minimum: float, maximum: float) -> float:
        base_delay = random.uniform(minimum, maximum)
        jitter = random.uniform(1.0 - self._delays.jitter_ratio, 1.0 + self._delays.jitter_ratio)
        return base_delay * jitter

    def _safe_type_character(self, character: str) -> None:
        self._validate_key_allowed(character)
        self._keyboard.type(character)

    def _safe_press_key(self, key: Key | KeyCode | str) -> None:
        self._validate_key_allowed(key)
        self._keyboard.press(key)

    def _safe_release_key(self, key: Key | KeyCode | str) -> None:
        self._validate_key_allowed(key)
        self._keyboard.release(key)

    def _validate_key_allowed(self, key: Key | KeyCode | str) -> None:
        if self._is_enter_or_return(key):
            self.stop()
            raise RuntimeError("Safety block: Enter/Return key emission is forbidden.")

    def _is_enter_or_return(self, key: Key | KeyCode | str) -> bool:
        if isinstance(key, str):
            return key in FORBIDDEN_TEXT_CHARACTERS

        if isinstance(key, KeyCode):
            if key.char in FORBIDDEN_CHARACTERS:
                return True
            if key.vk in {3, 13, 36, 76}:
                return True

        key_name = getattr(key, "name", "")
        return key_name in FORBIDDEN_KEY_NAMES

    def _wait_while_paused_or_stopped(self) -> None:
        while not self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.05)

    def _should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _sleep_interruptibly(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._should_stop():
                return False
            self._wait_while_paused_or_stopped()
            remaining = max(0.0, deadline - time.monotonic())
            time.sleep(min(0.05, remaining))
        return not self._should_stop()
