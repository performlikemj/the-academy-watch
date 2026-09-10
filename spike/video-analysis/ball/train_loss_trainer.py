"""Ultralytics adapter: checkpoint selection and early stopping see TRAIN loss only."""

from __future__ import annotations
import math


def train_loss_value(losses):
    values = losses.values() if isinstance(losses, dict) else losses
    total = sum(
        float(v.detach().cpu()) if hasattr(v, "detach") else float(v) for v in values
    )
    if not math.isfinite(total) or total < 0:
        raise ValueError("finite nonnegative training loss required")
    return total


def trainer_class():
    # Lazy imports keep saved-score and archive tests independent of torch.
    from ultralytics.models.yolo.detect.train import DetectionTrainer

    class TrainLossTrainer(DetectionTrainer):
        best_fitness: float | None

        def validate(self):
            loss = train_loss_value(self.tloss)
            fitness = 1.0 / (1.0 + loss)
            if self.best_fitness is None or fitness > self.best_fitness:
                self.best_fitness = fitness
            return {"train/selection_loss": loss}, fitness

        def final_eval(self):
            # No final held-out validator or best.pt evaluation inside training.
            return None

    return TrainLossTrainer
