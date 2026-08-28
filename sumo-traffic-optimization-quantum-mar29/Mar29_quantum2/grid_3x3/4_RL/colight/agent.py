import random
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

class CoLightNetwork(nn.Module):

    def __init__(
        self,
        state_size=14,
        hidden_size=64,
        action_size=2,
        num_intersections=4
    ):
        self.num_intersections = num_intersections
        self.hidden_size = hidden_size
        
        super().__init__()

        # -------------------------------------------------
        # Shared local intersection encoder
        # -------------------------------------------------
        self.local_encoder = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU()
        )

        self.attention_norm = nn.LayerNorm(hidden_size)

        # -------------------------------------------------
        # Graph-attention projections
        # -------------------------------------------------
        self.num_heads = 4
        self.head_dim = hidden_size // self.num_heads

        assert hidden_size % self.num_heads == 0

        self.query_layer = nn.Linear(hidden_size, hidden_size)
        self.key_layer = nn.Linear(hidden_size, hidden_size)
        self.value_layer = nn.Linear(hidden_size, hidden_size)

        self.attention_output = nn.Linear(
            hidden_size,
            hidden_size
        )

        # -------------------------------------------------
        # Q-value head
        # Converts each network-aware intersection
        # representation into Q(NS) and Q(EW)
        # -------------------------------------------------
        self.q_head = nn.Linear(
            hidden_size,
            action_size
        )

    def graph_attention(self, local_features, adjacency):
        batch_size = local_features.size(0)
        num_intersections = local_features.size(1)

        normalized_features = self.attention_norm(local_features)
        queries = self.query_layer(normalized_features)
        keys = self.key_layer(normalized_features)
        values = self.value_layer(normalized_features)

        # [B, N, H] -> [B, heads, N, head_dim]
        queries = queries.view(
            batch_size,
            num_intersections,
            self.num_heads,
            self.head_dim
        ).transpose(1, 2)

        keys = keys.view(
            batch_size,
            num_intersections,
            self.num_heads,
            self.head_dim
        ).transpose(1, 2)

        values = values.view(
            batch_size,
            num_intersections,
            self.num_heads,
            self.head_dim
        ).transpose(1, 2)

        # [B, heads, N, N]
        scores = torch.matmul(
            queries,
            keys.transpose(-2, -1)
        )

        scores = scores / (
            self.head_dim ** 0.5
        )

        # adjacency:
        # [N, N] -> [1, 1, N, N]
        mask = adjacency.unsqueeze(0).unsqueeze(0)

        scores = scores.masked_fill(
            mask == 0,
            float("-inf")
        )

        ATTENTION_TEMPERATURE = 2.0

        attention_weights = torch.softmax(
            scores / ATTENTION_TEMPERATURE,
            dim=-1
        )
        
        # [B, heads, N, head_dim]
        attended_features = torch.matmul(
            attention_weights,
            values
        )

        # Back to [B, N, H]
        attended_features = (
            attended_features
            .transpose(1, 2)
            .contiguous()
            .view(
                batch_size,
                num_intersections,
                self.hidden_size
            )
        )

        attended_features = self.attention_output(
            attended_features
        )

        return attended_features, attention_weights

    def forward(self, x, adjacency=None, return_attention=False):

        if x.dim() == 2:

            local_features = self.local_encoder(x)

            q_values = self.q_head(
                local_features
            )

            return q_values

        # -------------------------------------------------
        # CoLight graph behavior:
        #
        # x shape:
        # [batch_size, num_intersections, state_size]
        # -------------------------------------------------

        local_features = self.local_encoder(x)

        attended_features, attention_weights = (
            self.graph_attention(
                local_features,
                adjacency
            )
        )

        # Residual connection:
        # retain local information AND add neighbor info
        network_features = (
            local_features
            + attended_features
        )

        q_values = self.q_head(
            network_features
        )

        if return_attention:
            return q_values, attention_weights

        return q_values


class CoLightAgent:
    def __init__(
        self,
        state_size=14,
        action_size=2,
        learning_rate=0.0005,
        gamma=0.95,
        epsilon=1.0,
        epsilon_min=0.05,
        epsilon_decay=0.99,
        memory_size=50000,
        batch_size=64,
        target_update_interval=200,
        adjacency=None,
    ):
        self.state_size = state_size
        self.action_size = action_size

        self.model = CoLightNetwork(
            state_size=state_size,
            action_size=action_size
        )

        self.target_model = CoLightNetwork(
            state_size=state_size,
            action_size=action_size
        )

        self.adjacency = torch.tensor(
            adjacency,
            dtype=torch.float32
        )

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
    
    def select_actions(
        self,
        states
    ):
        # states shape:
        # [num_intersections, state_size]

        # -------------------------------------------------
        # Exploration
        # -------------------------------------------------
        if random.random() < self.epsilon:

            return [
                random.randrange(self.action_size)
                for _ in range(len(states))
            ]

        # -------------------------------------------------
        # Exploitation
        # -------------------------------------------------
        states_tensor = torch.tensor(
            states,
            dtype=torch.float32
        ).unsqueeze(0)

        with torch.no_grad():

            q_values = self.model(
                states_tensor,
                self.adjacency
            )

        # q_values shape:
        # [1, num_intersections, action_size]

        actions = torch.argmax(
            q_values,
            dim=2
        )

        return actions.squeeze(0).tolist()
    

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

        all_current_q = self.model(
            states,
            self.adjacency
        )

        current_q = all_current_q.gather(
            2,
            actions.unsqueeze(2)
        ).squeeze(2)


        with torch.no_grad():
            all_next_q = self.target_model(
                next_states,
                self.adjacency
            )

            next_q = all_next_q.max(
                dim=2
            )[0]

            done_mask = dones.unsqueeze(1)

            target_q = (
                rewards
                + self.gamma
                * next_q
                * (1.0 - done_mask)
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

        if self.training_steps == 0:

            print("\n===== COLIGHT REPLAY SHAPE CHECK =====")

            print("States shape:")
            print(states.shape)

            print("Actions shape:")
            print(actions.shape)

            print("Rewards shape:")
            print(rewards.shape)

            print("Next states shape:")
            print(next_states.shape)

            print("Dones shape:")
            print(dones.shape)

            print("===== END REPLAY SHAPE CHECK =====\n")


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
