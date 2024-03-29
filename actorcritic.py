import gymnasium as gym
import torch
import torch.nn as nn
import torch.optim as optim
from torch.nn.utils import clip_grad_norm_
from torch.distributions import Categorical, Normal
import numpy as np
import os
from collections import namedtuple
from time import time
from torch.utils.tensorboard import SummaryWriter

######################################################################
# 1. Define the Policy (Actor) and Value (Critic) Networks
class Network(nn.Module):
    def __init__(self, input_size, output_size, hidden_sizes=[64, 64], is_policy=True):
        super(Network, self).__init__()
        self.hidden_sizes = hidden_sizes
        layers = [nn.Linear(input_size, hidden_sizes[0]), nn.ReLU()]
        for i in range(len(hidden_sizes)-1):
            layers.append(nn.Linear(hidden_sizes[i], hidden_sizes[i+1]))
            layers.append(nn.ReLU())
        layers.append(nn.Linear(hidden_sizes[-1], output_size))
        
        self.network = nn.Sequential(*layers)
        self.is_policy = is_policy

    def forward(self, x):
        if self.is_policy:
            return nn.Softmax(dim=-1)(self.network(x))
        else:
            return self.network(x)

    def reinitialize_output_layer(self, output_size, freeze_hidden_layers=True):
        if freeze_hidden_layers:
            for param in self.network[:-1].parameters():
                param.requires_grad = False
        
        self.network[-1] = nn.Linear(self.hidden_sizes[-1], output_size)
        nn.init.normal_(self.network[-1].weight, mean=0., std=0.1)
        nn.init.constant_(self.network[-1].bias, 0)
        if self.is_policy:
            self.network.add_module("softmax", nn.Softmax(dim=-1))


######################################################################
#2. Reshape the environment wrapper to handle the action space
class EnvironmentWrapper:
    def __init__(self, env, target_state_size=6, target_action_size=3):
        self.env = env
        self.target_state_size = target_state_size
        self.target_action_size = target_action_size
        self.action_space = env.action_space.n if isinstance(env.action_space, gym.spaces.Discrete) else env.action_space.shape[0]

    def reset(self):
        state, _ = self.env.reset()
        # Pad state to match target_state_size
        padded_state = np.append(state, np.zeros(self.target_state_size - len(state)))
        return padded_state

    def step(self, action):
        action = min(self.action_space-1, max(0, action))
        
        state, reward, done, _, info = self.env.step(action)
        # Pad state to match target_state_size
        padded_state = np.append(state, np.zeros(self.target_state_size - len(state)))
        return padded_state, reward, done, info

    def action_padding(self, action):
        one_hot_action = np.zeros(self.target_action_size)
        one_hot_action[action] = 1
        return one_hot_action

######################################################################
# 3. Define the Agent
Transition = namedtuple("Transition", ["state", "action", "reward", "next_state", "done"])

class ActorCriticAgent:
    def __init__(self, config):
        self.device = torch.device(config['device'] if torch.cuda.is_available() else "cpu")
        self.policy_network = Network(config['state_size'], config['action_size'], config['hidden_sizes'], is_policy=True).to(self.device)
        self.value_network = Network(config['state_size'], 1, config['hidden_sizes'], is_policy=False).to(self.device)
        self.optimizer_actor = optim.Adam(self.policy_network.parameters(), lr=config['lr_actor'])
        self.optimizer_critic = optim.Adam(self.value_network.parameters(), lr=config['lr_critic'])
        self.verbosity = config['verbosity']
        self.env_name = config['env_name']
        self.writer = SummaryWriter(f"runs/{config['experiment']}")
        self.gamma = config['gamma']


    def select_action(self, state):
        # without gradients --  test
        with torch.no_grad():
            state = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            probs = self.policy_network(state)
            m = Categorical(probs)
            action = m.sample()

        return action.item(), m.log_prob(action)


    def update_policy(self, transitions):
        loss_policy = 0
        loss_value = 0

        for transition in transitions:
            state, action, reward, next_state, done = transition
            state = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            next_state = torch.FloatTensor(next_state).unsqueeze(0).to(self.device)
            action = torch.tensor([action]).to(self.device)
            reward = torch.tensor([reward], dtype=torch.float).to(self.device)
            done = torch.tensor([done], dtype=torch.float).to(self.device)

            # Compute value loss
            predicted_value = self.value_network(state)
            next_predicted_value = self.value_network(next_state)
            expected_value = reward + self.gamma * next_predicted_value * (1 - done)
            loss_value += nn.MSELoss()(predicted_value, expected_value.detach())

            # compute policy loss
            probs = self.policy_network(state)
            m = Categorical(probs)
            log_prob = m.log_prob(action)
            advantage = expected_value - predicted_value.detach()
            loss_policy += (-log_prob * advantage).mean()

        # Backpropagate losses
        self.optimizer_actor.zero_grad()
        loss_policy.backward()
        self.optimizer_actor.step()

        self.optimizer_critic.zero_grad()
        loss_value.backward()
        self.optimizer_critic.step()

        return loss_policy.item(), loss_value.item()

    def save_models(self, path='models'):
        if not os.path.exists(path):
            os.makedirs(path)
        torch.save(self.policy_network.state_dict(), os.path.join(path, f'{self.env_name}_policy_network.pth'))
        torch.save(self.value_network.state_dict(), os.path.join(path, f'{self.env_name}_value_network.pth'))

    def load_models(self, path='models', env_name='None'):
        if env_name == 'None':
            env_name = self.env_name
        self.policy_network.load_state_dict(torch.load(os.path.join(path, f'{env_name}_policy_network.pth'), map_location=self.device))
        self.value_network.load_state_dict(torch.load(os.path.join(path, f'{env_name}_value_network.pth'), map_location=self.device))

    def reinitialize_output_layers(self, new_action_size):
        """
        Reinitializes the output layers of both the policy and value networks
        for the new action size, freezing the hidden layers.
        """
        self.policy_network.reinitialize_output_layer(output_size=new_action_size)
        self.value_network.reinitialize_output_layer(output_size=1) # output_size is always 1 for the value network
        self.policy_network.to(self.device)
        self.value_network.to(self.device)


    def train(self, env_wrapper, max_episodes=1000, max_steps=500, reward_threshold=475.0, update_frequency=500):
        self.results = {'Episode': [], 'Reward': [], "Average_100": [], 'Solved': -1, 'Duration': 0, 'Loss': [], 'LossV': []}
        results = self.results
        start_time = time()
        episode_rewards = []
        total_steps = 0

        for episode in range(max_episodes):
            state = env_wrapper.reset()
            episode_reward = 0
            transitions = []

            for step in range(max_steps):
                action, log_prob = self.select_action(state)
                next_state, reward, done, _ = env_wrapper.step(action)
                transitions.append(Transition(state, action, reward, next_state, done))

                episode_reward += reward
                state = next_state

                # update policy
                if (len(transitions) >= update_frequency) or done:
                    loss_policy, loss_value = self.update_policy(transitions)
                    results['Loss'].append(loss_policy)
                    results['LossV'].append(loss_value)
                    transitions = [] # should we reset the transitions list here?

                if done:
                    break

            episode_rewards.append(episode_reward)

            results['Episode'].append(episode)
            results['Reward'].append(episode_reward)

            if len(episode_rewards) >= 100:
                avg_reward = sum(episode_rewards[-100:]) / 100
                results['Average_100'].append(avg_reward)
                if avg_reward > reward_threshold and results['Solved'] == -1:
                    results['Solved'] = episode
                    print(f"Solved at episode {episode} with average reward {avg_reward}.")
                    break
            else:
                results['Average_100'].append(sum(episode_rewards) / len(episode_rewards))

            if episode % self.verbosity == 0:
                print(f"Episode {episode}, Avg Reward: {results['Average_100'][-1]}, PLoss: {loss_policy}, VLoss: {loss_value}")

            # Log to TensorBoard
            self.writer.add_scalar("Reward", episode_reward, episode)
            self.writer.add_scalar("Average_100", results['Average_100'][-1], episode)
            self.writer.add_scalar("Loss_Policy", loss_policy, episode)
            self.writer.add_scalar("Loss_Value", loss_value, episode)

        results['Duration'] = time() - start_time
        self.writer.close()

        return results


class ContinuousActorCriticAgent(ActorCriticAgent):
    def __init__(self, config):
        super().__init__(config)
        # Ensure the policy network is suitable for continuous action spaces
        self.policy_network = Network(config['state_size'], config['action_size'], config['hidden_sizes'], discrete=False).to(self.device)
        
    def select_action(self, state):
        # Adjust for continuous action space
        state = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        action_mean, action_std = self.policy_network(state)
        dist = Normal(action_mean, action_std.exp())
        action = dist.sample()
        log_prob = dist.log_prob(action).sum(-1)
        return action.cpu().detach().numpy(), log_prob

    def update_policy(self, transitions):
        loss_policy = 0
        loss_value = 0

        for transition in transitions:
            state, action, reward, next_state, done = transition
            state = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            next_state = torch.FloatTensor(next_state).unsqueeze(0).to(self.device)
            action = torch.FloatTensor(action).unsqueeze(0).to(self.device)
            reward = torch.FloatTensor([reward]).to(self.device)
            done = torch.FloatTensor([done]).to(self.device)

            # Compute value loss as before
            predicted_value = self.value_network(state)
            next_predicted_value = self.value_network(next_state)
            expected_value = reward + self.gamma * next_predicted_value * (1 - done)
            loss_value += nn.MSELoss()(predicted_value.squeeze(), expected_value.detach().squeeze())

            # Adjust policy loss computation for continuous action space
            action_mean, action_std = self.policy_network(state)
            dist = Normal(action_mean, action_std.exp())
            log_prob = dist.log_prob(action).sum(-1, keepdim=True)
            advantage = expected_value - predicted_value.detach()
            loss_policy += (-log_prob * advantage).mean()

        # Perform backpropagation and optimization as before
        self.optimizer_actor.zero_grad()
        loss_policy.backward()
        self.optimizer_actor.step()

        self.optimizer_critic.zero_grad()
        loss_value.backward()
        self.optimizer_critic.step()

        return loss_policy.item(), loss_value.item()
    



###################################################################
# for legacy purposes will be deleted
#     import gymnasium as gym
# import torch
# import torch.nn as nn
# import torch.optim as optim
# from torch.nn.utils import clip_grad_norm_
# from torch.distributions import Categorical, Normal
# import numpy as np
# import os
# from collections import namedtuple
# from time import time
# from torch.utils.tensorboard import SummaryWriter

# ######################################################################
# # 1. Define the Policy (Actor) and Value (Critic) Networks
# class PolicyNetwork(nn.Module):
#     def __init__(self, input_size, output_size, hidden_sizes=[64, 128], discrete=True):
#         super(PolicyNetwork, self).__init__()
#         self.discrete = discrete
#         layers = []
#         prev_size = input_size
#         for hidden_size in hidden_sizes:
#             layers.append(nn.Linear(prev_size, hidden_size))
#             layers.append(nn.ReLU())
#             prev_size = hidden_size

#         layers.append(nn.Linear(hidden_sizes[-1], output_size))

#         self.network = nn.Sequential(*layers)
        
#         if not discrete:
#             # For continuous actions, also define log_std but don't use it unless needed
#             self.log_std = nn.Parameter(torch.zeros(output_size))
        
#     def forward(self, x):
#         output = self.network(x)
#         if self.discrete:
#             # Use softmax for discrete action spaces
#             return nn.Softmax(dim=-1)(output)
#         else:
#             # For continuous action spaces, output mean and log standard deviation
#             return output, self.log_std


# class ValueNetwork(nn.Module):
#     def __init__(self, input_size, output_size=1, hidden_sizes=[64, 128]):
#         super(ValueNetwork, self).__init__()
#         layers = []
#         prev_size = input_size
#         for hidden_size in hidden_sizes:
#             layers.append(nn.Linear(prev_size, hidden_size))
#             layers.append(nn.ReLU())
#             prev_size = hidden_size
#         layers.append(nn.Linear(hidden_sizes[-1], output_size))
#         self.network = nn.Sequential(*layers)

#     def forward(self, x):
#         return self.network(x)


# ######################################################################
# #2. Reshape the enviroment wrapper to handle the action space
# class EnvironmentWrapper:
#     def __init__(self, env, target_state_size=6, target_action_size=3):
#         self.env = env
#         self.target_state_size = target_state_size
#         self.target_action_size = target_action_size
#         self.action_space = env.action_space.n if isinstance(env.action_space, gym.spaces.Discrete) else env.action_space.shape[0]

#     def reset(self):
#         state, _ = self.env.reset()
#         # Pad state to match target_state_size
#         padded_state = np.append(state, np.zeros(self.target_state_size - len(state)))
#         return padded_state

#     def step(self, action):
#         action = min(self.action_space-1, max(0, action))
        
#         state, reward, done, _, info = self.env.step(action)
#         # Pad state to match target_state_size
#         padded_state = np.append(state, np.zeros(self.target_state_size - len(state)))
#         return padded_state, reward, done, info

#     def action_padding(self, action):
#         one_hot_action = np.zeros(self.target_action_size)
#         one_hot_action[action] = 1
#         return one_hot_action

# ######################################################################
# # 3. Define the Agent
# Transition = namedtuple("Transition", ["state", "action", "reward", "next_state", "done"])

# class ActorCriticAgent:
#     def __init__(self, config):
#         self.device = torch.device(config['device'] if torch.cuda.is_available() else "cpu")
#         self.policy_network = PolicyNetwork(config['state_size'], config['action_size'], config['hidden_sizes']).to(self.device)
#         self.value_network = ValueNetwork(config['state_size'], output_size=1, hidden_sizes=config['hidden_sizes']).to(self.device)

#         self.optimizer_actor = optim.Adam(self.policy_network.parameters(), lr=config['lr_actor'])
#         self.optimizer_critic = optim.Adam(self.value_network.parameters(), lr=config['lr_critic'])
#         self.verbosity = config['verbosity']
#         self.env_name = config['env_name']
#         self.writer = SummaryWriter(f"runs/{config['experiment']}")
#         self.gamma = config['gamma']

#     def select_action(self, state):
#         state = torch.FloatTensor(state).unsqueeze(0).to(self.device)
#         probs = self.policy_network(state)
#         m = Categorical(probs)
#         action = m.sample()
#         return action.item(), m.log_prob(action)


#     def update_policy(self, transitions):
#         loss_policy = 0
#         loss_value = 0

#         for transition in transitions:
#             state, action, reward, next_state, done = transition
#             state = torch.FloatTensor(state).unsqueeze(0).to(self.device)
#             next_state = torch.FloatTensor(next_state).unsqueeze(0).to(self.device)
#             action = torch.tensor([action]).to(self.device)
#             reward = torch.tensor([reward], dtype=torch.float).to(self.device)
#             done = torch.tensor([done], dtype=torch.float).to(self.device)

#             # Compute value loss
#             predicted_value = self.value_network(state)
#             next_predicted_value = self.value_network(next_state)
#             expected_value = reward + self.gamma * next_predicted_value * (1 - done)
#             loss_value += nn.MSELoss()(predicted_value, expected_value.detach())


#             probs = self.policy_network(state)
#             m = Categorical(probs)
#             log_prob = m.log_prob(action)
#             advantage = expected_value - predicted_value.detach()
#             loss_policy += (-log_prob * advantage).mean()

#         # Backpropagate losses
#         self.optimizer_actor.zero_grad()
#         loss_policy.backward()
#         self.optimizer_actor.step()

#         self.optimizer_critic.zero_grad()
#         loss_value.backward()
#         self.optimizer_critic.step()

#         return loss_policy.item(), loss_value.item()

#     def save_models(self, path='models'):
#         if not os.path.exists(path):
#             os.makedirs(path)
#         torch.save(self.policy_network.state_dict(), os.path.join(path, f'{self.env_name}_policy_network.pth'))
#         torch.save(self.value_network.state_dict(), os.path.join(path, f'{self.env_name}_value_network.pth'))

#     def load_models(self, path='models', env_name='None'):
#         if env_name == 'None':
#             env_name = self.env_name
#         self.policy_network.load_state_dict(torch.load(os.path.join(path, f'{env_name}_policy_network.pth'), map_location=self.device))
#         self.value_network.load_state_dict(torch.load(os.path.join(path, f'{env_name}_value_network.pth'), map_location=self.device))

#     def train(self, env_wrapper, max_episodes=1000, max_steps=500, reward_threshold=475.0, update_frequency=500):
#         self.results = {'Episode': [], 'Reward': [], "Average_100": [], 'Solved': -1, 'Duration': 0, 'Loss': [], 'LossV': []}
#         results = self.results
#         start_time = time()
#         episode_rewards = []
#         total_steps = 0

#         for episode in range(max_episodes):
#             state = env_wrapper.reset()
#             episode_reward = 0
#             transitions = []

#             for step in range(max_steps):
#                 action, log_prob = self.select_action(state)
#                 next_state, reward, done, _ = env_wrapper.step(action)
#                 transitions.append(Transition(state, action, reward, next_state, done))

#                 episode_reward += reward
#                 state = next_state

#                 # update policy
#                 if (len(transitions) >= update_frequency) or done:
#                     loss_policy, loss_value = self.update_policy(transitions)
#                     results['Loss'].append(loss_policy)
#                     results['LossV'].append(loss_value)
#                     transitions = []

#                 if done:
#                     break

#             episode_rewards.append(episode_reward)

#             results['Episode'].append(episode)
#             results['Reward'].append(episode_reward)

#             if len(episode_rewards) >= 100:
#                 avg_reward = sum(episode_rewards[-100:]) / 100
#                 results['Average_100'].append(avg_reward)
#                 if avg_reward > reward_threshold and results['Solved'] == -1:
#                     results['Solved'] = episode
#                     print(f"Solved at episode {episode} with average reward {avg_reward}.")
#                     break
#             else:
#                 results['Average_100'].append(sum(episode_rewards) / len(episode_rewards))

#             if episode % self.verbosity == 0:
#                 print(f"Episode {episode}, Avg Reward: {results['Average_100'][-1]}, PLoss: {loss_policy}, VLoss: {loss_value}")

#             # Log to TensorBoard
#             self.writer.add_scalar("Reward", episode_reward, episode)
#             self.writer.add_scalar("Average_100", results['Average_100'][-1], episode)
#             self.writer.add_scalar("Loss_Policy", loss_policy, episode)
#             self.writer.add_scalar("Loss_Value", loss_value, episode)

#         results['Duration'] = time() - start_time
#         self.writer.close()

#         return results