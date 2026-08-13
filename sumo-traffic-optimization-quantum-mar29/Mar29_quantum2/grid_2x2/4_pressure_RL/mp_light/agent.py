import random
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

NS_MOVEMENTS = [0, 1, 2, 6, 7, 8]
EW_MOVEMENTS = [3, 4, 5, 9, 10, 11]

class MPLightNetwork(nn.Module):

    def __init__(self, state_size=13, action_size=2):
        super().__init__()

        # Same encoder is used for both phases.
        # Each phase contains 6 movement pressures.
        self.phase_encoder = nn.Sequential(
            nn.Linear(6, 32),
            nn.ReLU(),
            nn.Linear(32, 32),
            nn.ReLU()
        )

        # Competition network compares:
        # NS representation
        # EW representation
        # current active phase
        self.competition_scorer = nn.Sequential(
            nn.Linear(32 + 32 + 1, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )

    def forward(self, x):

        # First 12 values are movement pressures
        movement_pressures = x[:, :12]

        # Final value is current phase
        current_phase = x[:, 12].unsqueeze(1)

        # Extract movements belonging to each competing phase
        ns_pressures = movement_pressures[:, NS_MOVEMENTS]
        ew_pressures = movement_pressures[:, EW_MOVEMENTS]

        # IMPORTANT:
        # Both phases go through the SAME encoder
        ns_features = self.phase_encoder(ns_pressures)
        ew_features = self.phase_encoder(ew_pressures)

        # Is the candidate phase currently active?
        ns_is_current = (current_phase == 0).float()
        ew_is_current = (current_phase == 1).float()

        # -------------------------------------------------
        # Explicit phase competition
        # -------------------------------------------------

        # Score NS while treating EW as its competitor
        ns_vs_ew = torch.cat(
            [
                ns_features,
                ew_features,
                ns_is_current
            ],
            dim=1
        )

        q_ns = self.competition_scorer(
            ns_vs_ew
        )

        # Score EW while treating NS as its competitor
        ew_vs_ns = torch.cat(
            [
                ew_features,
                ns_features,
                ew_is_current
            ],
            dim=1
        )

        q_ew = self.competition_scorer(
            ew_vs_ns
        )

        # Combine into [Q_NS, Q_EW]
        q_values = torch.cat(
            [
                q_ns,
                q_ew
            ],
            dim=1
        )

        return q_values


class MPLightAgent:
    def __init__(
        self,
        state_size=13,
        action_size=2,
        learning_rate=0.001,
        gamma=0.95,
        epsilon=1.0,
        epsilon_min=0.05,
        epsilon_decay=0.97,
        memory_size=10000,
        batch_size=64,
        target_update_interval=200,
    ):
        self.state_size = state_size
        self.action_size = action_size

        self.model = MPLightNetwork(state_size, action_size)
        self.target_model = MPLightNetwork(state_size, action_size)
        self.target_model.load_state_dict(self.model.state_dict())
        self.target_model.eval()

        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=learning_rate
        )

        self.loss_function = nn.MSELoss()

        self.memory = deque(maxlen=memory_size)

        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size

        self.target_update_interval = target_update_interval
        self.training_steps = 0

    def select_action(self, state):
        # Exploration
        if random.random() < self.epsilon:
            return random.randrange(self.action_size)

        # Exploitation
        state_tensor = torch.tensor(
            state,
            dtype=torch.float32
        ).unsqueeze(0)

        with torch.no_grad():
            q_values = self.model(state_tensor)

        return int(torch.argmax(q_values, dim=1).item())

    def remember(self, state, action, reward, next_state, done):
        self.memory.append(
            (
                state,
                action,
                reward,
                next_state,
                done,
            )
        )

    def train_step(self):
        if len(self.memory) < self.batch_size:
            return None

        batch = random.sample(
            self.memory,
            self.batch_size
        )

        states = []
        actions = []
        rewards = []
        next_states = []
        dones = []

        for state, action, reward, next_state, done in batch:
            states.append(state)
            actions.append(action)
            rewards.append(reward)
            next_states.append(next_state)
            dones.append(done)

        states = torch.tensor(
            np.asarray(states),
            dtype=torch.float32
        )

        actions = torch.tensor(
            actions,
            dtype=torch.long
        )

        rewards = torch.tensor(
            rewards,
            dtype=torch.float32
        )

        next_states = torch.tensor(
            np.asarray(next_states),
            dtype=torch.float32
        )

        dones = torch.tensor(
            dones,
            dtype=torch.float32
        )

        current_q = (
            self.model(states)
            .gather(1, actions.unsqueeze(1))
            .squeeze(1)
        )

        with torch.no_grad():
            next_q = self.target_model(next_states).max(1)[0]

            target_q = (
                rewards
                + self.gamma * next_q * (1.0 - dones)
            )

        loss = nn.SmoothL1Loss()(
            current_q,
            target_q
        )

        self.optimizer.zero_grad()
        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            self.model.parameters(),
            max_norm=1.0
        )

        self.optimizer.step()

        self.training_steps += 1

        if self.training_steps % self.target_update_interval == 0:
            self.update_target_network()

        return loss.item()

    def update_target_network(self):
        self.target_model.load_state_dict(
            self.model.state_dict()
        )

    def decay_epsilon(self):
        self.epsilon = max(
            self.epsilon_min,
            self.epsilon * self.epsilon_decay
        )

    def save(self, path):
        torch.save(
            self.model.state_dict(),
            path
        )

    def load(self, path):
        state_dict = torch.load(
            path,
            map_location="cpu"
        )

        self.model.load_state_dict(state_dict)
        self.target_model.load_state_dict(state_dict)

    def set_evaluation_mode(self):
        self.epsilon = 0.0
        self.model.eval()
        self.target_model.eval()
