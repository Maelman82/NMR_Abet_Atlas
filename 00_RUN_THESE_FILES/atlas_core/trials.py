from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from .common import norm_key, norm_text, to_float

OUTCOME_MAP = {
    "hit": "Hit",
    "missed hit": "Miss",
    "mistake": "False Alarm",
    "correct rejection": "Correct Rejection",
    "correction trial correct rejection": "Correction Trial Correct Rejection",
    "correction trial mistake": "Correction Trial Mistake",
}

STATE_EFFECTS = {
    "stimulus_duration": "stimulus_duration",
    "current_image": "Current_Image",
    "correct_image": "Correct_Image",
    "current_iti": "Current_ITI",
    "_trial_counter": "_Trial_Counter",
    "correct_grid_position": "Correct_Grid_Position",
}


@dataclass
class Trial:
    trial_index: int
    trial_counter: Optional[float] = None
    stimulus_onset: Optional[float] = None
    outcome_time: Optional[float] = None
    outcome: str = ""
    stimulus_duration_s: Optional[float] = None
    current_image: Optional[float] = None
    correct_image: Optional[float] = None
    current_iti_s: Optional[float] = None
    correct_grid_position: Optional[float] = None
    hit: int = 0
    miss: int = 0
    false_alarm: int = 0
    correct_rejection: int = 0
    correction_trial_correct_rejection: int = 0
    correction_trial_mistake: int = 0
    response_latency_s: Optional[float] = None
    reward_retrieval_latency_s: Optional[float] = None


def reconstruct_trials(events: list[dict[str, Any]]) -> list[Trial]:
    """Reconstruct CPT-like image-presentation trials without filtering or IQR cleaning.

    Sessions that do not use the observed CPT 'Display Image' event pattern simply
    return zero reconstructed trials. Their session remains fully indexed and its
    cached SQLite source remains available for future task-specific modules.
    """
    state: dict[str, Optional[float]] = {
        "stimulus_duration": None,
        "Current_Image": None,
        "Correct_Image": None,
        "Current_ITI": None,
        "_Trial_Counter": None,
        "Correct_Grid_Position": None,
    }
    trials: list[Trial] = []
    current: Optional[Trial] = None

    for e in events:
        effect = norm_text(e.get("DEffectText"))
        key = effect.lower()
        dtime = to_float(e.get("DTime"))
        for _, effect_name in STATE_EFFECTS.items():
            if key == effect_name.lower():
                state[effect_name] = to_float(e.get("DValue1"))

        if key == "display image":
            if current is not None:
                trials.append(current)
            current = Trial(
                trial_index=len(trials) + 1,
                trial_counter=state.get("_Trial_Counter"),
                stimulus_onset=dtime,
                stimulus_duration_s=state.get("stimulus_duration"),
                current_image=state.get("Current_Image"),
                correct_image=state.get("Correct_Image"),
                current_iti_s=state.get("Current_ITI"),
                correct_grid_position=state.get("Correct_Grid_Position"),
            )
            continue

        outcome_label = OUTCOME_MAP.get(key)
        if outcome_label and current is not None and not current.outcome:
            current.outcome = outcome_label
            current.outcome_time = dtime
            if outcome_label == "Hit": current.hit = 1
            elif outcome_label == "Miss": current.miss = 1
            elif outcome_label == "False Alarm": current.false_alarm = 1
            elif outcome_label == "Correct Rejection": current.correct_rejection = 1
            elif outcome_label == "Correction Trial Correct Rejection": current.correction_trial_correct_rejection = 1
            elif outcome_label == "Correction Trial Mistake": current.correction_trial_mistake = 1
            if current.stimulus_onset is not None and dtime is not None and outcome_label in {"Hit", "False Alarm"}:
                current.response_latency_s = dtime - current.stimulus_onset
            trials.append(current)
            current = None

    if current is not None:
        trials.append(current)

    retrieval_times = [
        to_float(e.get("DTime")) for e in events
        if norm_key(e.get("DEffectText")) == "reward collected start iti"
    ]
    retrieval_times = [x for x in retrieval_times if x is not None]
    hit_trials = [t for t in trials if t.hit == 1 and t.outcome_time is not None]
    ridx = 0
    for t in hit_trials:
        while ridx < len(retrieval_times) and retrieval_times[ridx] < float(t.outcome_time):
            ridx += 1
        if ridx < len(retrieval_times):
            dt = retrieval_times[ridx] - float(t.outcome_time)
            if 0 <= dt < 30:
                t.reward_retrieval_latency_s = dt
                ridx += 1
    return trials


def trial_dict(trial: Trial) -> dict[str, Any]:
    return asdict(trial)
