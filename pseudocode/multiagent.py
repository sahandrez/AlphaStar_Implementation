"""Library for multiagent concerns."""
import collections
import numpy as np
import random

from pysc2.lib import actions, features, units
from utils import get_entity_obs, get_upgrade_obs, get_gameloop_obs, get_race_onehot, get_agent_statistics
from network import EntityEncoder, ScalarEncoder, SpatialEncoder, Core


_SELECT_ARMY = actions.FUNCTIONS.select_army.id
_SELECT_ALL = [0]

_MOVE_SCREEN = actions.FUNCTIONS.Move_screen.id
_NOT_QUEUED = [0]
_QUEUED = [1]
_SELECT_ALL = [2]

_SELECT_POINT = actions.FUNCTIONS.select_point.id
_ATTACK_SCREEN = actions.FUNCTIONS.Attack_screen.id
_ATTACK_MINIMAP = actions.FUNCTIONS.Attack_minimap.id
_SELECT_CONTROL_GROUP = actions.FUNCTIONS.select_control_group.id

_BUILD_SUPPLY_DEPOT = actions.FUNCTIONS.Build_SupplyDepot_screen.id
_BUILD_BARRACKS = actions.FUNCTIONS.Build_Barracks_screen.id
_BUILD_REFINERY = actions.FUNCTIONS.Build_Refinery_screen.id
_BUILD_TECHLAB = actions.FUNCTIONS.Build_TechLab_screen.id

_TRAIN_MARINE = actions.FUNCTIONS.Train_Marine_quick.id
_TRAIN_MARAUDER = actions.FUNCTIONS.Train_Marauder_quick.id
_TRAIN_SCV = actions.FUNCTIONS.Train_SCV_quick.id
_SELECT_ARMY = actions.FUNCTIONS.select_army.id
_SELECT_IDLE_WORKER = actions.FUNCTIONS.select_idle_worker.id

_RETURN_SCV = actions.FUNCTIONS.Harvest_Return_SCV_quick.id
_HARVEST_GATHER = actions.FUNCTIONS.Harvest_Gather_screen.id
_HARVEST_GATHER_SCV = actions.FUNCTIONS.Harvest_Gather_SCV_screen.id


class Agent(object):
  """Demonstrates agent interface.

  In practice, this needs to be instantiated with the right neural network
  architecture.
  """
  def __init__(self, race, initial_weights):
    self.race = race
    self.steps = 0
    self.weights = initial_weights
    self.weights = None

    self.spatial_encoder = SpatialEncoder(img_height=128, img_width=128, channel=27)
    self.scalar_encoder = ScalarEncoder(128)
    self.entity_encoder = EntityEncoder(464, 8)
    self.core = Core(12)

    self.home_upgrade_array = np.zeros(89)
    self.away_upgrade_array = np.zeros(89)

  def initial_state(self):
    """Returns the hidden state of the agent for the start of an episode."""
    # Network details elided.
    initial_state = None

    return initial_state

  def set_weights(self, weights):
    self.weights = weights

  def get_weights(self):
    return self.weights

  def get_steps(self):
    """How many agent steps the agent has been trained for."""
    return self.steps

  def step(self, observation, last_state):
    """Performs inference on the observation, given hidden state last_state."""
    # We are omitting the details of network inference here.
    # ...
    feature_screen = observation[3]['feature_screen']
    feature_minimap = observation[3]['feature_minimap']
    feature_units = observation[3]['feature_units']
    feature_player = observation[3]['player']
    available_actions = observation[3]['available_actions']
    score_by_category = observation[3]['score_by_category']
    game_loop = observation[3]['game_loop']

    unit_type = feature_screen.unit_type
    empty_space = np.where(unit_type == 0)
    empty_space = np.vstack((empty_space[0], empty_space[1])).T
    random_point = random.choice(empty_space)
    #target = [random_point[0], random_point[1]]
    #action = [actions.FunctionCall(_BUILD_SUPPLY_DEPOT, [_NOT_QUEUED, target])]
    policy_logits = None
    new_state = None

    spatial_encoder_output = self.spatial_encoder(np.reshape(feature_screen, [1,128,128,27]))

    agent_statistics = get_agent_statistics(score_by_category)

    home_race = 'Terran'
    away_race = 'Terran'
    race = get_race_onehot(home_race, away_race)

    time = get_gameloop_obs(game_loop)

    upgrade_value = get_upgrade_obs(feature_units)
    if upgrade_value != -1:
      self.home_upgrade_array[np.where(upgrade_value[0] == 1)] = 1
      self.away_upgrade_array[np.where(upgrade_value[1] == 1)] = 1

    embedded_scalar = np.concatenate((agent_statistics, race, time, self.home_upgrade_array, self.away_upgrade_array), axis=0)
    scalar_encoder_output = self.scalar_encoder(np.reshape(embedded_scalar, [1,307]))
    embedded_feature_units = get_entity_obs(feature_units)
    entity_encoder_output = self.entity_encoder(np.reshape(embedded_feature_units, [1,512,464]))
    encoder_input = np.concatenate((spatial_encoder_output, scalar_encoder_output, entity_encoder_output), axis=1)

    core_input = np.reshape(encoder_input, [16, 8, 131])
    whole_seq_output, final_memory_state, final_carry_state = self.core(core_input)
    print(whole_seq_output.shape)
    print(final_memory_state.shape)
    print(final_carry_state.shape)

    action = [actions.FUNCTIONS.no_op()]

    return action, policy_logits, new_state

  def unroll(self, trajectory):
    """Unrolls the network over the trajectory.

    The actions taken by the agent and the initial state of the unroll are
    dictated by trajectory.
    """
    # We omit the details of network inference here.
    return policy_logits, baselines


def remove_monotonic_suffix(win_rates, players):
  if not win_rates:
    return win_rates, players

  for i in range(len(win_rates) - 1, 0, -1):
    if win_rates[i - 1] < win_rates[i]:
      return win_rates[:i + 1], players[:i + 1]

  return np.array([]), []


def pfsp(win_rates, weighting="linear"):
  weightings = {
      "variance": lambda x: x * (1 - x),
      "linear": lambda x: 1 - x,
      "linear_capped": lambda x: np.minimum(0.5, 1 - x),
      "squared": lambda x: (1 - x)**2,
  }
  fn = weightings[weighting]
  probs = fn(np.asarray(win_rates))
  norm = probs.sum()
  if norm < 1e-10:
    return np.ones_like(win_rates) / len(win_rates)

  return probs / norm


class Payoff:
  def __init__(self):
    self._players = []
    self._wins = collections.defaultdict(lambda: 0)
    self._draws = collections.defaultdict(lambda: 0)
    self._losses = collections.defaultdict(lambda: 0)
    self._games = collections.defaultdict(lambda: 0)
    self._decay = 0.99

  def _win_rate(self, _home, _away):
    if self._games[_home, _away] == 0:
      return 0.5

    return (self._wins[_home, _away] +
            0.5 * self._draws[_home, _away]) / self._games[_home, _away]

  def __getitem__(self, match):
    home, away = match

    if isinstance(home, Player):
      home = [home]
    if isinstance(away, Player):
      away = [away]

    win_rates = np.array([[self._win_rate(h, a) for a in away] for h in home])
    if win_rates.shape[0] == 1 or win_rates.shape[1] == 1:
      win_rates = win_rates.reshape(-1)

    return win_rates

  def update(self, home, away, result):
    for stats in (self._games, self._wins, self._draws, self._losses):
      stats[home, away] *= self._decay
      stats[away, home] *= self._decay

    self._games[home, away] += 1
    self._games[away, home] += 1
    if result == "win":
      self._wins[home, away] += 1
      self._losses[away, home] += 1
    elif result == "draw":
      self._draws[home, away] += 1
      self._draws[away, home] += 1
    else:
      self._wins[away, home] += 1
      self._losses[home, away] += 1

  def add_player(self, player):
    self._players.append(player)

  @property
  def players(self):
    return self._players


class Player(object):
  def get_match(self):
    pass

  def ready_to_checkpoint(self):
    return False

  def _create_checkpoint(self):
    return Historical(self, self.payoff)

  @property
  def payoff(self):
    return self._payoff

  @property
  def race(self):
    return self._race

  def checkpoint(self):
    raise NotImplementedError


class MainPlayer(Player):
  def __init__(self, race, agent, payoff):
    self.agent = Agent(race, agent.get_weights())
    self._payoff = payoff
    self._race = agent.race
    self._checkpoint_step = 0

  def _pfsp_branch(self):
    historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical)
    ]
    win_rates = self._payoff[self, historical]
    return np.random.choice(
        historical, p=pfsp(win_rates, weighting="squared")), True

  def _selfplay_branch(self, opponent):
    # Play self-play match
    if self._payoff[self, opponent] > 0.3:
      return opponent, False

    # If opponent is too strong, look for a checkpoint
    # as curriculum
    historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical) and player.parent == opponent
    ]
    win_rates = self._payoff[self, historical]
    return np.random.choice(
        historical, p=pfsp(win_rates, weighting="variance")), True

  def _verification_branch(self, opponent):
    # Check exploitation
    exploiters = set([
        player for player in self._payoff.players
        if isinstance(player, MainExploiter)
    ])
    exp_historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical) and player.parent in exploiters
    ]
    win_rates = self._payoff[self, exp_historical]
    if len(win_rates) and win_rates.min() < 0.3:
      return np.random.choice(
          exp_historical, p=pfsp(win_rates, weighting="squared")), True

    # Check forgetting
    historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical) and player.parent == opponent
    ]
    win_rates = self._payoff[self, historical]
    win_rates, historical = remove_monotonic_suffix(win_rates, historical)
    if len(win_rates) and win_rates.min() < 0.7:
      return np.random.choice(
          historical, p=pfsp(win_rates, weighting="squared")), True

    return None

  def step(self, observation, state):
    action, policy_logits, new_state = self.agent.step(observation, state)
    return action, policy_logits, new_state

  def initial_state(self):
    """Returns the hidden state of the agent for the start of an episode."""
    # Network details elided.
    return self.agent.initial_state()

  def get_weights(self):
    return self.agent.get_weights()

  def get_race(self):
    return self._race

  def get_match(self):
    coin_toss = np.random.random()

    # Make sure you can beat the League
    if coin_toss < 0.5:
      return self._pfsp_branch()

    main_agents = [
        player for player in self._payoff.players
        if isinstance(player, MainPlayer)
    ]
    opponent = np.random.choice(main_agents)

    # Verify if there are some rare players we omitted
    if coin_toss < 0.5 + 0.15:
      request = self._verification_branch(opponent)
      if request is not None:
        return request

    return self._selfplay_branch(opponent)

  def ready_to_checkpoint(self):
    steps_passed = self.agent.get_steps() - self._checkpoint_step
    if steps_passed < 2e9:
      return False

    historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical)
    ]
    win_rates = self._payoff[self, historical]
    return win_rates.min() > 0.7 or steps_passed > 4e9

  def checkpoint(self):
    self._checkpoint_step = self.agent.get_steps()
    return self._create_checkpoint()


class MainExploiter(Player):
  def __init__(self, race, agent, payoff):
    self.agent = Agent(race, agent.get_weights())
    self._initial_weights = agent.get_weights()
    self._payoff = payoff
    self._race = agent.race
    self._checkpoint_step = 0

  def step(self, observation, state):
    action, policy_logits, new_state = self.agent.step(observation, state)
    return action, policy_logits, new_state

  def initial_state(self):
    """Returns the hidden state of the agent for the start of an episode."""
    # Network details elided.
    return self.agent.initial_state()

  def get_match(self):
    main_agents = [
        player for player in self._payoff.players
        if isinstance(player, MainPlayer)
    ]
    opponent = np.random.choice(main_agents)

    if self._payoff[self, opponent] > 0.1:
      return opponent, True

    historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical) and player.parent == opponent
    ]
    win_rates = self._payoff[self, historical]

    return np.random.choice(
        historical, p=pfsp(win_rates, weighting="variance")), True

  def get_race(self):
    return self._race

  def checkpoint(self):
    self.agent.set_weights(self._initial_weights)
    self._checkpoint_step = self.agent.get_steps()
    return self._create_checkpoint()

  def ready_to_checkpoint(self):
    steps_passed = self.agent.get_steps() - self._checkpoint_step
    if steps_passed < 2e9:
      return False

    main_agents = [
        player for player in self._payoff.players
        if isinstance(player, MainPlayer)
    ]
    win_rates = self._payoff[self, main_agents]
    return win_rates.min() > 0.7 or steps_passed > 4e9


class LeagueExploiter(Player):
  def __init__(self, race, agent, payoff):
    self.agent = Agent(race, agent.get_weights())
    self._initial_weights = agent.get_weights()
    self._payoff = payoff
    self._race = agent.race
    self._checkpoint_step = 0

  def step(self, observation, state):
    action, policy_logits, new_state = self.agent.step(observation, state)
    return action, policy_logits, new_state

  def initial_state(self):
    """Returns the hidden state of the agent for the start of an episode."""
    # Network details elided.
    return self.agent.initial_state()

  def get_match(self):
    historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical)
    ]
    win_rates = self._payoff[self, historical]
    return np.random.choice(
        historical, p=pfsp(win_rates, weighting="linear_capped")), True

  def get_race(self):
    return self._race

  def checkpoint(self):
    if np.random.random() < 0.25:
      self.agent.set_weights(self._initial_weights)
    self._checkpoint_step = self.agent.get_steps()
    return self._create_checkpoint()

  def ready_to_checkpoint(self):
    steps_passed = self._agent.get_steps() - self._checkpoint_step
    if steps_passed < 2e9:
      return False
    historical = [
        player for player in self._payoff.players
        if isinstance(player, Historical)
    ]
    win_rates = self._payoff[self, historical]
    return win_rates.min() > 0.7 or steps_passed > 4e9


class Historical(Player):
  def __init__(self, agent, payoff):
    self._agent = Agent(agent.race, agent.get_weights())
    self._payoff = payoff
    self._race = agent.race
    self._parent = agent

  def step(self, observation, state):
    action, policy_logits, new_state = self._agent.step(observation, state)
    return action, policy_logits, new_state

  @property
  def parent(self):
    return self._parent

  def initial_state(self):
    """Returns the hidden state of the agent for the start of an episode."""
    # Network details elided.
    return self._agent.initial_state()

  def get_match(self):
    raise ValueError("Historical players should not request matches")

  def ready_to_checkpoint(self):
    return False


class League(object):
  def __init__(self,
               initial_agents,
               main_agents=1,
               main_exploiters=1,
               league_exploiters=1):
    self._payoff = Payoff()
    self._learning_agents = []

    for race in initial_agents:

      for _ in range(main_agents):
        main_agent = MainPlayer(race, initial_agents[race], self._payoff)

        self._learning_agents.append(main_agent)
        self._payoff.add_player(main_agent.checkpoint())

      for _ in range(main_exploiters):
        self._learning_agents.append(
            MainExploiter(race, initial_agents[race], self._payoff))

      for _ in range(league_exploiters):
        self._learning_agents.append(
            LeagueExploiter(race, initial_agents[race], self._payoff))

    for player in self._learning_agents:
      self._payoff.add_player(player)

  def update(self, home, away, result):
    return self._payoff.update(home, away, result)

  def get_player(self, idx):
    return self._learning_agents[idx]

  def add_player(self, player):
    self._payoff.add_player(player)
