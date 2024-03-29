## **TODO**
1. fix MCC baseline
2. fix cartpole2mcc
3. run acrobot2cartpole until convergence
4. test progressive with multiple adapter architectures acromcc2cartpole
5. create and run cartpole+acrobot2mcc notebook
6. extract tensorboard results for all experiments
7. report
8. cleanup code



# Deep Reinforcement Learning for Classic Control Problems

Welcome to our project repository, where we explore the fascinating world of Deep Reinforcement Learning (DRL) applied to a set of classic control problems. Our journey takes us through the realms of CartPole, Acrobot, and MountainCarContinuous environments, demonstrating the power and versatility of DRL strategies in navigating these challenges.

## Project Overview

The core of our project revolves around implementing and refining Actor-Critic architectures to master three distinct environments provided by the OpenAI Gym. Each environment presents unique challenges:

- **CartPole**: Balance a pole on a moving cart.
- **Acrobot**: Swing a two-link robot arm to reach a certain height.
- **MountainCarContinuous**: Drive an underpowered car up a steep mountain.

Our approach is twofold: first, we tailor an Actor-Critic model to learn efficient policies for each environment. Then, we delve into the realms of transfer learning and progressive neural networks to share knowledge between models, enhancing learning efficiency and performance across tasks.

## Key Features

- **Modular DRL Framework**: We've developed a flexible DRL framework that allows for easy switching between discrete and continuous action spaces, making it adaptable across a wide range of environments.
- **Transfer Learning Capabilities**: Our project showcases the implementation of simplified progressive neural networks, enabling the transfer of learned features from one task to efficiently bootstrap learning in another.
- **Exploration Strategies**: To tackle the challenges of continuous action spaces, we've experimented with Ornstein-Uhlenbeck noise and other techniques to balance exploration and exploitation.

## Installation and Usage

Begin by cloning this repository to your local machine. Our codebase is built using Python 3.8+, PyTorch, and OpenAI Gym. Ensure these prerequisites are met by installing the necessary packages:

```
git clone https://github.com/your-repo/deep-rl-classic-control.git
cd deep-rl-classic-control
pip install -r requirements.txt
```

To start training a model on a specific environment, run:

```
python train.py --env CartPole-v1
```

Replace `CartPole-v1` with `Acrobot-v1` or `MountainCarContinuous-v0` as desired. The training script includes options for customizing the learning rate, number of episodes, and other parameters, which can be accessed via `--help`.

## Project Structure

- `models/`: Contains the neural network architectures for the policy and value functions.
- `agents/`: Implementation of the Actor-Critic and Enhanced Actor-Critic agents.
- `utils/`: Utility functions and classes for environment wrapping, data handling, and more.
- `train.py`: The main training script for launching experiments.
- `requirements.txt`: Lists all the necessary Python packages.

## Results and Analysis

We meticulously logged all training sessions using TensorBoard, allowing us to track performance metrics, loss convergence, and other vital statistics. Our findings reveal the impact of transfer learning in reducing training time and improving overall model performance across tasks.

## Challenges and Future Directions

While our models have achieved notable successes, continuous action spaces remain a challenging frontier. Future work will explore advanced algorithms such as TD3 and PPO, as well as experimenting with different exploration strategies and reward shaping techniques.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Embark on this DRL adventure with us, and let's push the boundaries of what's possible in classic control problems together!
