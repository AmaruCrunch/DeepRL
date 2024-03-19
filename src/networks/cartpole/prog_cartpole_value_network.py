import gymnasium as gym
import numpy as np
import tensorflow as tf
from datetime import datetime
import time
# from torch.utils.tensorboard import SummaryWriter
# from logger import Logger
import json
import os
import src.config as config


class ProgCartpoleValueNetwork:

    def __init__(self, learning_rate, name='value_network'):
        self.state_size = 6
        self.learning_rate = learning_rate

        with tf.compat.v1.variable_scope(name):
            self.state = tf.compat.v1.placeholder(tf.float32, [None, self.state_size], name="state")
            self.R_t = tf.compat.v1.placeholder(tf.float32, name="total_rewards")

            # First column - Acrobot NN
            self.restore_acrobat_value_weights()
            self.h1_k1 = tf.nn.elu(tf.add(tf.matmul(self.state, self.W1_k1), self.b1_k1))

            # Second column - MountainCar NN
            self.restore_mcc_value_weights()
            self.h1_k2 = tf.nn.elu(tf.add(tf.matmul(self.state, self.W1_k2), self.b1_k2))
            self.uk2_h1_k1 = tf.compat.v1.get_variable("uk2_h1_k1", [self.b1_k1.shape[0], self.b2_k2.shape[0]], initializer=tf.initializers.GlorotUniform(seed=0))
            self.h2_k2 = tf.nn.relu(tf.add(tf.add(tf.matmul(self.h1_k2, self.W2_k2), self.b2_k2), tf.matmul(self.h1_k1, self.uk2_h1_k1)))

            # Third column - Cartpole NN
            self.init_weights()
            self.h1 = tf.nn.elu(tf.add(tf.matmul(self.state, self.W1), self.b1))
            self.uk3_h1_k1 = tf.compat.v1.get_variable("uk3_h1_k1", [self.b1_k1.shape[0], self.b2.shape[0]], initializer=tf.initializers.GlorotUniform(seed=0))
            self.uk3_h1_k2 = tf.compat.v1.get_variable("uk3_h1_k2", [self.b1_k2.shape[0], self.b2.shape[0]], initializer=tf.initializers.GlorotUniform(seed=0))
            self.h2 = tf.nn.relu(tf.add(tf.add(tf.matmul(self.h1, self.W2), self.b2), tf.add(tf.matmul(self.h1_k1, self.uk3_h1_k1), tf.matmul(self.h1_k2, self.uk3_h1_k2))))
            self.uk3_h2_k2 = tf.compat.v1.get_variable("uk3_h2_k2", [self.b2_k2.shape[0], self.b3.shape[0]], initializer=tf.initializers.GlorotUniform(seed=0))
            self.output = tf.add(tf.add(tf.matmul(self.h2, self.W3), self.b3), tf.matmul(self.h2_k2, self.uk3_h2_k2))

            self.loss = tf.compat.v1.losses.mean_squared_error(self.R_t, self.output)
            self.optimizer = tf.compat.v1.train.AdamOptimizer(learning_rate=self.learning_rate).minimize(self.loss)

    def init_weights(self):
        hidden_1 = 64
        self.W1 = tf.compat.v1.get_variable("W1", [self.state_size, hidden_1], initializer=tf.initializers.GlorotUniform(seed=0))
        self.b1 = tf.compat.v1.get_variable("b1", [hidden_1], initializer=tf.zeros_initializer())
        self.W2 = tf.compat.v1.get_variable("W2", [hidden_1, hidden_1], initializer=tf.initializers.GlorotUniform(seed=0))
        self.b2 = tf.compat.v1.get_variable("b2", [hidden_1], initializer=tf.zeros_initializer())
        self.W3 = tf.compat.v1.get_variable("W3", [hidden_1, 1], initializer=tf.initializers.GlorotUniform(seed=0))
        self.b3 = tf.compat.v1.get_variable("b3", [1], initializer=tf.zeros_initializer())

    def restore_mcc_value_weights(self):
        with open(config.mcc_value_weights, 'r') as f:
            weights = json.load(f)
        self.W1_k2 = tf.compat.v1.get_variable("W1_k2", initializer=tf.constant(weights["W1"]), trainable=False)
        self.b1_k2 = tf.compat.v1.get_variable("b1_k2", initializer=tf.constant(weights["b1"]), trainable=False)
        self.W2_k2 = tf.compat.v1.get_variable("W2_k2", initializer=tf.constant(weights["W2"]), trainable=False)
        self.b2_k2 = tf.compat.v1.get_variable("b2_k2", initializer=tf.constant(weights["b2"]), trainable=False)
        self.W3_k2 = tf.compat.v1.get_variable("W3_k2", initializer=tf.constant(weights["W3"]), trainable=False)
        self.b3_k2 = tf.compat.v1.get_variable("b3_k2", initializer=tf.constant(weights["b3"]), trainable=False)

    def restore_acrobat_value_weights(self):
        with open(config.acrobot_value_weights, 'r') as f:
            weights = json.load(f)
        self.W1_k1 = tf.compat.v1.get_variable("W1_k1", initializer=tf.constant(weights["W1"]), trainable=False)
        self.b1_k1 = tf.compat.v1.get_variable("b1_k1", initializer=tf.constant(weights["b1"]), trainable=False)
        self.W2_k1 = tf.compat.v1.get_variable("W2_k1", initializer=tf.constant(weights["W2"]), trainable=False)
        self.b2_k1 = tf.compat.v1.get_variable("b2_k1", initializer=tf.constant(weights["b2"]), trainable=False)
        self.W3_k1 = tf.compat.v1.get_variable("W3_k1", initializer=tf.constant(weights["W2"]), trainable=False)
        self.b3_k1 = tf.compat.v1.get_variable("b3_k1", initializer=tf.constant(weights["b2"]), trainable=False)
