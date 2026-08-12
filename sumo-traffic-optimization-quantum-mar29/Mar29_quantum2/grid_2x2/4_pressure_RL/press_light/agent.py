import random
import numpy as np


# ============================================================
# PURE NUMPY NEURAL NETWORK
# ============================================================

class PressLightNetwork:

    def __init__(
        self,
        state_size=5,
        action_size=2,
        hidden_size=64
    ):

        self.state_size = state_size
        self.action_size = action_size
        self.hidden_size = hidden_size

        # ----------------------------------------------------
        # Layer 1: 5 -> 64
        # Similar initialization scale to PyTorch nn.Linear
        # ----------------------------------------------------

        limit1 = 1.0 / np.sqrt(state_size)

        self.W1 = np.random.uniform(
            -limit1,
            limit1,
            (state_size, hidden_size)
        ).astype(np.float32)

        self.b1 = np.random.uniform(
            -limit1,
            limit1,
            hidden_size
        ).astype(np.float32)


        # ----------------------------------------------------
        # Layer 2: 64 -> 64
        # ----------------------------------------------------

        limit2 = 1.0 / np.sqrt(hidden_size)

        self.W2 = np.random.uniform(
            -limit2,
            limit2,
            (hidden_size, hidden_size)
        ).astype(np.float32)

        self.b2 = np.random.uniform(
            -limit2,
            limit2,
            hidden_size
        ).astype(np.float32)


        # ----------------------------------------------------
        # Output layer: 64 -> 2
        # ----------------------------------------------------

        limit3 = 1.0 / np.sqrt(hidden_size)

        self.W3 = np.random.uniform(
            -limit3,
            limit3,
            (hidden_size, action_size)
        ).astype(np.float32)

        self.b3 = np.random.uniform(
            -limit3,
            limit3,
            action_size
        ).astype(np.float32)


    def forward(
        self,
        x,
        return_cache=False
    ):

        x = np.asarray(
            x,
            dtype=np.float32
        )

        # Allow one state:
        #
        # [5]
        #
        # or a batch:
        #
        # [batch_size, 5]

        if x.ndim == 1:

            x = x.reshape(
                1,
                -1
            )


        # ----------------------------------------------------
        # Layer 1
        # ----------------------------------------------------

        z1 = (
            x @ self.W1
            + self.b1
        )

        a1 = np.maximum(
            z1,
            0.0
        )


        # ----------------------------------------------------
        # Layer 2
        # ----------------------------------------------------

        z2 = (
            a1 @ self.W2
            + self.b2
        )

        a2 = np.maximum(
            z2,
            0.0
        )


        # ----------------------------------------------------
        # Output Q-values
        # ----------------------------------------------------

        q_values = (
            a2 @ self.W3
            + self.b3
        )


        if return_cache:

            cache = (
                x,
                z1,
                a1,
                z2,
                a2
            )

            return (
                q_values,
                cache
            )


        return q_values


    def copy_from(
        self,
        other
    ):

        self.W1 = other.W1.copy()
        self.b1 = other.b1.copy()

        self.W2 = other.W2.copy()
        self.b2 = other.b2.copy()

        self.W3 = other.W3.copy()
        self.b3 = other.b3.copy()



# ============================================================
# PRESSLIGHT DQN AGENT
# ============================================================

class PressLightAgent:

    def __init__(
        self,
        state_size=5,
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


        # ----------------------------------------------------
        # Main Q-network
        # ----------------------------------------------------

        self.model = PressLightNetwork(
            state_size=state_size,
            action_size=action_size
        )


        # ----------------------------------------------------
        # Target Q-network
        # ----------------------------------------------------

        self.target_model = PressLightNetwork(
            state_size=state_size,
            action_size=action_size
        )

        self.target_model.copy_from(
            self.model
        )


        # ----------------------------------------------------
        # Replay memory
        # ----------------------------------------------------

        self.memory = []

        self.memory_size = memory_size

        self.memory_position = 0


        # ----------------------------------------------------
        # DQN hyperparameters
        # ----------------------------------------------------

        self.gamma = gamma

        self.epsilon = epsilon

        self.epsilon_min = epsilon_min

        self.epsilon_decay = epsilon_decay

        self.batch_size = batch_size

        self.learning_rate = learning_rate


        self.target_update_interval = (
            target_update_interval
        )

        self.training_steps = 0


        # ----------------------------------------------------
        # Adam optimizer parameters
        # ----------------------------------------------------

        self.adam_beta1 = 0.9

        self.adam_beta2 = 0.999

        self.adam_epsilon = 1e-8

        self.adam_step = 0


        # Adam first moment

        self.adam_m = {}

        # Adam second moment

        self.adam_v = {}


        for name in (
            "W1",
            "b1",
            "W2",
            "b2",
            "W3",
            "b3"
        ):

            value = getattr(
                self.model,
                name
            )

            self.adam_m[name] = (
                np.zeros_like(value)
            )

            self.adam_v[name] = (
                np.zeros_like(value)
            )


    # ========================================================
    # ACTION SELECTION
    # ========================================================

    def select_action(
        self,
        state
    ):

        # ----------------------------------------------------
        # Exploration
        # ----------------------------------------------------

        if random.random() < self.epsilon:

            return random.randrange(
                self.action_size
            )


        # ----------------------------------------------------
        # Exploitation
        # ----------------------------------------------------

        q_values = self.model.forward(
            state
        )


        return int(
            np.argmax(
                q_values[0]
            )
        )


    # ========================================================
    # REPLAY MEMORY
    # ========================================================

    def remember(
        self,
        state,
        action,
        reward,
        next_state,
        done
    ):

        experience = (

            np.asarray(
                state,
                dtype=np.float32
            ).copy(),

            int(action),

            float(reward),

            np.asarray(
                next_state,
                dtype=np.float32
            ).copy(),

            bool(done),
        )


        # ----------------------------------------------------
        # Fill replay buffer
        # ----------------------------------------------------

        if len(self.memory) < self.memory_size:

            self.memory.append(
                experience
            )

        else:

            # Circular replay buffer once full

            self.memory[
                self.memory_position
            ] = experience


        self.memory_position = (
            self.memory_position + 1
        ) % self.memory_size


    # ========================================================
    # HUBER LOSS
    # ========================================================

    @staticmethod
    def _huber_loss_and_gradient(
        prediction,
        target
    ):

        error = (
            prediction
            - target
        )

        abs_error = np.abs(
            error
        )


        # Equivalent to:
        #
        # PyTorch SmoothL1Loss(beta=1.0)

        losses = np.where(

            abs_error < 1.0,

            0.5 * error * error,

            abs_error - 0.5
        )


        gradient = np.where(

            abs_error < 1.0,

            error,

            np.sign(error)
        )


        # SmoothL1Loss uses mean reduction

        gradient = (
            gradient
            / prediction.shape[0]
        )


        return (
            float(np.mean(losses)),
            gradient.astype(np.float32)
        )


    # ========================================================
    # GRADIENT CLIPPING
    # ========================================================

    @staticmethod
    def _clip_gradients(
        grads,
        max_norm=1.0
    ):

        squared_norm = 0.0


        for grad in grads.values():

            squared_norm += float(
                np.sum(
                    grad * grad
                )
            )


        total_norm = np.sqrt(
            squared_norm
        )


        if total_norm > max_norm:

            scale = (
                max_norm
                / (total_norm + 1e-8)
            )


            for name in grads:

                grads[name] *= scale


    # ========================================================
    # ADAM OPTIMIZER
    # ========================================================

    def _adam_update(
        self,
        grads
    ):

        self.adam_step += 1


        beta1 = self.adam_beta1

        beta2 = self.adam_beta2


        for name, grad in grads.items():


            # ------------------------------------------------
            # First moment
            # ------------------------------------------------

            self.adam_m[name] = (

                beta1
                * self.adam_m[name]

                +

                (1.0 - beta1)
                * grad
            )


            # ------------------------------------------------
            # Second moment
            # ------------------------------------------------

            self.adam_v[name] = (

                beta2
                * self.adam_v[name]

                +

                (1.0 - beta2)
                * (grad * grad)
            )


            # ------------------------------------------------
            # Bias correction
            # ------------------------------------------------

            m_hat = (

                self.adam_m[name]

                /

                (
                    1.0
                    - beta1 ** self.adam_step
                )
            )


            v_hat = (

                self.adam_v[name]

                /

                (
                    1.0
                    - beta2 ** self.adam_step
                )
            )


            parameter = getattr(
                self.model,
                name
            )


            # ------------------------------------------------
            # Adam update
            # ------------------------------------------------

            parameter -= (

                self.learning_rate
                * m_hat

                /

                (
                    np.sqrt(v_hat)
                    + self.adam_epsilon
                )
            )


    # ========================================================
    # TRAINING
    # ========================================================

    def train_step(self):

        # ----------------------------------------------------
        # Need enough samples for a minibatch
        # ----------------------------------------------------

        if len(self.memory) < self.batch_size:

            return None


        # ----------------------------------------------------
        # Sample replay memory
        # ----------------------------------------------------

        batch = random.sample(
            self.memory,
            self.batch_size
        )


        states = np.asarray(

            [
                experience[0]
                for experience in batch
            ],

            dtype=np.float32
        )


        actions = np.asarray(

            [
                experience[1]
                for experience in batch
            ],

            dtype=np.int64
        )


        rewards = np.asarray(

            [
                experience[2]
                for experience in batch
            ],

            dtype=np.float32
        )


        next_states = np.asarray(

            [
                experience[3]
                for experience in batch
            ],

            dtype=np.float32
        )


        dones = np.asarray(

            [
                experience[4]
                for experience in batch
            ],

            dtype=np.float32
        )


        # ----------------------------------------------------
        # Current network:
        #
        # Q(s, a)
        # ----------------------------------------------------

        all_q_values, cache = (
            self.model.forward(
                states,
                return_cache=True
            )
        )


        batch_rows = np.arange(
            self.batch_size
        )


        current_q = all_q_values[
            batch_rows,
            actions
        ]


        # ----------------------------------------------------
        # Target network:
        #
        # r + gamma * max Q_target(s', a')
        # ----------------------------------------------------

        next_q_values = (
            self.target_model.forward(
                next_states
            )
        )


        max_next_q = np.max(
            next_q_values,
            axis=1
        )


        target_q = (

            rewards

            +

            self.gamma
            * max_next_q
            * (1.0 - dones)
        )


        # ----------------------------------------------------
        # Huber loss
        # ----------------------------------------------------

        loss, d_selected_q = (
            self._huber_loss_and_gradient(
                current_q,
                target_q
            )
        )


        # Only the Q-value associated with the chosen action
        # receives a gradient.

        d_q_values = np.zeros_like(
            all_q_values,
            dtype=np.float32
        )


        d_q_values[
            batch_rows,
            actions
        ] = d_selected_q


        # ----------------------------------------------------
        # BACKPROPAGATION
        # ----------------------------------------------------

        (
            x,
            z1,
            a1,
            z2,
            a2
        ) = cache


        # ----------------------------------------------------
        # Output layer
        # ----------------------------------------------------

        dW3 = (
            a2.T
            @ d_q_values
        )


        db3 = np.sum(
            d_q_values,
            axis=0
        )


        da2 = (
            d_q_values
            @ self.model.W3.T
        )


        # ReLU derivative

        dz2 = (
            da2
            * (z2 > 0.0)
        )


        # ----------------------------------------------------
        # Hidden layer 2
        # ----------------------------------------------------

        dW2 = (
            a1.T
            @ dz2
        )


        db2 = np.sum(
            dz2,
            axis=0
        )


        da1 = (
            dz2
            @ self.model.W2.T
        )


        dz1 = (
            da1
            * (z1 > 0.0)
        )


        # ----------------------------------------------------
        # Hidden layer 1
        # ----------------------------------------------------

        dW1 = (
            x.T
            @ dz1
        )


        db1 = np.sum(
            dz1,
            axis=0
        )


        grads = {

            "W1": dW1.astype(
                np.float32
            ),

            "b1": db1.astype(
                np.float32
            ),

            "W2": dW2.astype(
                np.float32
            ),

            "b2": db2.astype(
                np.float32
            ),

            "W3": dW3.astype(
                np.float32
            ),

            "b3": db3.astype(
                np.float32
            ),
        }


        # ----------------------------------------------------
        # Gradient clipping
        # ----------------------------------------------------

        self._clip_gradients(
            grads,
            max_norm=1.0
        )


        # ----------------------------------------------------
        # Adam optimizer update
        # ----------------------------------------------------

        self._adam_update(
            grads
        )


        # ----------------------------------------------------
        # Target network synchronization
        # ----------------------------------------------------

        self.training_steps += 1


        if (
            self.training_steps
            % self.target_update_interval
            == 0
        ):

            self.update_target_network()


        return loss


    # ========================================================
    # TARGET NETWORK
    # ========================================================

    def update_target_network(self):

        self.target_model.copy_from(
            self.model
        )


    # ========================================================
    # EPSILON DECAY
    # ========================================================

    def decay_epsilon(self):

        self.epsilon = max(

            self.epsilon_min,

            self.epsilon
            * self.epsilon_decay
        )


    # ========================================================
    # SAVE MODEL
    # ========================================================

    def save(
        self,
        path
    ):

        # Opening the file manually prevents NumPy from
        # automatically adding ".npz" to the filename.

        with open(
            path,
            "wb"
        ) as file:

            np.savez(

                file,

                W1=self.model.W1,
                b1=self.model.b1,

                W2=self.model.W2,
                b2=self.model.b2,

                W3=self.model.W3,
                b3=self.model.b3,
            )


    # ========================================================
    # LOAD MODEL
    # ========================================================

    def load(
        self,
        path
    ):

        with np.load(path) as data:

            self.model.W1 = (
                data["W1"]
                .astype(np.float32)
            )

            self.model.b1 = (
                data["b1"]
                .astype(np.float32)
            )

            self.model.W2 = (
                data["W2"]
                .astype(np.float32)
            )

            self.model.b2 = (
                data["b2"]
                .astype(np.float32)
            )

            self.model.W3 = (
                data["W3"]
                .astype(np.float32)
            )

            self.model.b3 = (
                data["b3"]
                .astype(np.float32)
            )


        self.update_target_network()


    # ========================================================
    # EVALUATION MODE
    # ========================================================

    def set_evaluation_mode(self):

        # No dropout or batch normalization exists in this
        # NumPy network, so evaluation mode only needs to
        # disable epsilon-greedy exploration.

        self.epsilon = 0.0