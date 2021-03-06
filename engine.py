"""
NOTES AND DEFINITIONS

round: each time an affection token is given, one round has ended
game: each time a player reaches AFFECTION_GOAL, one game has ended
match: a set of games, ending at a given number of wins

deck = [CARD_RANK, CARD_RANK, ..., CARD_RANK] # burner is not separate, is just the last card

player_action = {
    card: CARD_RANK, 
    ?target_player: player_idx, 
    ?guess: CARD_RANK
}

game_history = [
  {
    player: INT,
    player_action,
    ?eliminated_player: INT
  }
]

"""

from random import shuffle, randint
from copy import copy
from itertools import permutations
import sys

from bots.IdiotBot import IdiotBot
# from bots.MarkBot import MarkBot
# from bots.BenBot1 import BenBot
# from bots.BsonBot import BsonBot
from common import (full_deck, get_card_name,
                    GUARD, PRIEST, BARON, HANDMAID, PRINCE, KING, COUNTESS, PRINCESS, SUICIDE,
                    AFFECTION_GOAL, mprint)


class GameState(object):
    def __init__(self, players, affections):
        self.players = players
        player_states = []
        for player_idx, player in enumerate(players):
            player_states.append(PlayerState(player_idx, player, affections[player_idx]))

        game_deck = [card for card in full_deck()]
        shuffle(game_deck)
        self.deck = game_deck

        self.player_states = player_states
        self.history = []
        self.turn_record = None
        self.current_player_idx = -1  # TO DO: respect last winner

    def __str__(self):
        player_descriptions = "\r\n".join([player.short_description() for player in self.player_states])
        return """GAME STATE:
%s
deck: %r,
current player idx: %d
""" % (player_descriptions, self.deck, self.current_player_idx)

    def deal_card(self, player_idx):
        card = self.deck.pop(0)
        self.player_states[player_idx].hand.append(card)

    def advance_current_player(self):
        self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
        while not self.player_states[self.current_player_idx].is_alive:
            self.current_player_idx = (self.current_player_idx + 1) % len(self.players)

    def eliminate_player(self, player_idx, reason=None):
        mprint("Eliminating player %d" % player_idx, 4)
        if reason:
            mprint("Reason: %s" % reason, 4)
        mprint(lvl=4)
        self.turn_record['eliminated_player'] = player_idx

        player_state = self.player_states[player_idx]
        player_state.is_alive = False
        player_state.graveyard.extend(player_state.hand)
        player_state.hand = []

    def get_winner(self):
        remaining_players = [idx for idx, player_state in enumerate(self.player_states) if player_state.is_alive]
        if len(remaining_players) == 0:
            sys.exit("Everyone was eliminated. This is not supposed to happen.")

        elif len(remaining_players) == 1:
            return remaining_players[0]

        elif len(self.deck) < 2:
            player_states = {player_idx: self.player_states[player_idx] for player_idx in remaining_players}
            high_card = max([player_state.hand[0] for _, player_state in player_states.iteritems()])
            top_players = [player_idx for player_idx, player_state in player_states.iteritems() if player_state.hand[0] == high_card]

            if len(top_players) == 1:
                return top_players[0]
            else:
                winning_player = None
                max_graveyard_score = -1
                for player_idx in top_players:
                    graveyard_score = sum(player_states[player_idx].graveyard)
                    if graveyard_score > max_graveyard_score:
                        winning_player = player_idx
                        max_graveyard_score = graveyard_score
                return winning_player
        return None

    def get_available_targets(self):
        available_targets = []
        for idx, p_state in enumerate(self.player_states):
            if idx != self.current_player_idx and p_state.is_alive and not p_state.handmaided:
                available_targets.append(idx)
        return available_targets

    def sanitize_action(self, player_action):
        if 'card' not in player_action:
            player_action['card'] = None

        played_card = player_action['card']
        target = player_action.get('target_player')

        available_targets = self.get_available_targets()

        if played_card != GUARD:
            player_action['guess'] = None
        if target is not None:
            if played_card not in [GUARD, PRIEST, BARON, PRINCE, KING]:
                player_action['target_player'] = None
        if len(available_targets) == 0 and played_card != PRINCE:
            player_action['target_player'] = None

        return player_action

    def get_action_error(self, player_action):

        def target_is_valid():
            if len(available_targets) > 0:
                if target not in available_targets:
                    return False
            elif not isinstance(target, int) and target is not None:
                return False
            if target == self.current_player_idx:
                return False

            return True

        current_player_state = self.player_states[self.current_player_idx]

        played_card = player_action['card']
        target = player_action.get('target_player')
        guess = player_action.get('guess')
        available_targets = self.get_available_targets()

        # is choice of card valid?
        if played_card not in current_player_state.hand:
            return "played card not in hand"

        if played_card == GUARD:
            if not target_is_valid():
                return "invalid guard target"
            if len(available_targets) > 0 and (not isinstance(guess, int) or guess < 2 or guess > 8):
                return "invalid guard guess"

        elif played_card in [PRIEST, BARON, KING]:
            if not target_is_valid():
                return "invalid target"

        elif played_card == PRINCE:
            if not target_is_valid() and target != self.current_player_idx:
                return "invalid prince target"

        if played_card in [PRINCE, KING] and COUNTESS in current_player_state.hand:
            return "countess cheating"

        return None


class PublicGameState(object):
    def __init__(self, game_state):
        self.player_states = [PublicPlayerState(p) for p in game_state.player_states]
        self.cards_remaining = len(game_state.deck)
        self.history = [copy(record) for record in game_state.history]
        self.current_player_idx = game_state.current_player_idx

    def __str__(self):
        players = "\r\n".join([player.short_description() for player in self.player_states])
        return """
GAME STATE:
%s
cards remaining: %d,
current player idx: %d,
history: %r
        """ % (players, self.cards_remaining, self.current_player_idx, self.history)


class PlayerState(object):
    def __init__(self, idx, player, affection):
        self.my_idx = idx
        self.name = player.name
        self.graveyard = []
        self.is_alive = True
        self.affection = affection
        self.hand = []
        self.handmaided = False

    def __str__(self):
        return """
P%d %s
hand: %r
is_alive: %r
handmaided: %r
graveyard: %r
affection: %d
        """ % (self.my_idx, self.name, self.hand, self.is_alive, self.handmaided, self.graveyard, self.affection)

    def short_description(self):
        alive = "alive" if self.is_alive else "dead"
        handmaided = "handmaided, " if self.handmaided else ""
        affection = "<3" * self.affection
        return "P%d (%s): %s, %s%r %s" % (self.my_idx, self.name, alive, handmaided, self.hand, affection)


class PublicPlayerState(object):
    def __init__(self, player_state):
        self.player_idx = player_state.my_idx
        self.graveyard = player_state.graveyard
        self.is_alive = player_state.is_alive
        self.affection = player_state.affection
        self.handmaided = player_state.handmaided

    def __str__(self):
        return """
P%d
is_alive: %r
handmaided: %r
graveyard: %r
affection: %d
        """ % (self.player_idx, self.is_alive, self.handmaided, self.graveyard, self.affection)

    def short_description(self):
        alive = "alive" if self.is_alive else "dead"
        handmaided = ", handmaided" if self.handmaided else ""
        return "P%d: %s%s" % (self.player_idx, alive, handmaided)


def describe_action(action, player_idx):
    targeting = ""
    guessing = ""

    if action.get('target_player') is not None:
        targeting = " Target: P%d." % action['target_player']
    if action.get('guess') is not None:
        guessing = " Guess: %s." % get_card_name(action['guess'])

    return "ACTION: P%d plays %s.%s%s" % (player_idx, get_card_name(action['card']), targeting, guessing)


def play_round(players, affections, starting_player=None):

    if starting_player is None:
        starting_player = randint(0, len(players) - 1)
    starting_player -= 1  # it's gonna be incremented anyway

    mprint("BEGINNING ROUND", 4)
    mprint(lvl=4)

    game_state = GameState(players, affections)
    for player_idx, _ in enumerate(players):
        game_state.deal_card(player_idx)

    winner = None

    # play a round
    while winner is None:

        # whose turn is it?
        game_state.advance_current_player()
        current_player_idx = game_state.current_player_idx
        current_player = players[current_player_idx]
        current_player_state = game_state.player_states[current_player_idx]

        # every turn housekeeping
        current_player_state.handmaided = False
        game_state.turn_record = {}

        game_state.deal_card(current_player_idx)
        public_game_state = PublicGameState(game_state)

        mprint(game_state, 4)

        player_action = current_player.play_turn(current_player_state.hand, public_game_state)
        player_action = game_state.sanitize_action(player_action)
        mprint(describe_action(player_action, current_player_idx), 5)
        mprint(lvl=5)
        action_error = game_state.get_action_error(player_action)

        if action_error is not None:
            game_state.eliminate_player(current_player_idx, action_error)
            game_state.turn_record = {
                'player_idx': current_player_idx,
                'action': {'card': SUICIDE},
                'eliminated_player': current_player_idx
            }

        else:  # valid move, carry on
            played_card = player_action['card']
            target = player_action.get('target_player')
            guess = player_action.get('guess')

            target_player_state = game_state.player_states[target] if target is not None else None

            game_state.turn_record = {
                'player_idx': current_player_idx,
                'action': player_action,
                'eliminated_player': None
            }

            current_player_state.hand.remove(played_card)
            current_player_state.graveyard.append(played_card)

            if played_card == GUARD:
                if target is not None:
                    if guess in target_player_state.hand:
                        game_state.eliminate_player(target, "guessed by guard")

            elif played_card == PRIEST:
                if target is not None:
                    current_player.learn(target, target_player_state.hand, len(game_state.history))

            elif played_card == BARON:
                if target is not None:
                    my_card = current_player_state.hand[0]
                    their_card = target_player_state.hand[0]

                    if my_card != their_card:
                        loser = target if my_card > their_card else current_player_idx
                        game_state.eliminate_player(loser, "outranked in baron-off")

            elif played_card == HANDMAID:
                current_player_state.handmaided = True

            elif played_card == PRINCE:
                discarded = target_player_state.hand.pop(0)
                target_player_state.graveyard.append(discarded)

                if discarded == PRINCESS:
                    game_state.eliminate_player(target, "discarded princess")
                else:
                    game_state.deal_card(target)

            elif played_card == KING:
                if target is not None:
                    my_card = current_player_state.hand.pop()
                    current_player_state.hand.append(target_player_state.hand.pop())
                    target_player_state.hand.append(my_card)

            elif played_card == COUNTESS:
                pass

            elif played_card == PRINCESS:
                game_state.eliminate_player(current_player_idx, "played princess")

        # update history
        game_state.history.append(game_state.turn_record)

        # check for winner
        winner = game_state.get_winner()

    mprint("Round over. Winner: Player %d" % winner, 3)
    mprint(lvl=3)
    return winner


def play_game(players):
    mprint("BEGINING GAME", 2)
    mprint(lvl=2)
    for p in players:
        p.reset()
    affections = [0 for _ in players]
    winner = None
    while max(affections) < AFFECTION_GOAL:
        winner = play_round(players, affections, winner)
        affections[winner] += 1

    mprint("END OF GAME", 2)
    mprint("Final affection scores:", 2)
    mprint(affections, 2)
    return affections.index(AFFECTION_GOAL)


def play_match(players, num_games):
    wins = [0 for _ in players]
    for _ in xrange(num_games):
        winner = play_game(players)
        wins[winner] += 1

    return wins


def play_tournament(games_per_match):
    player_match_wins = {cls_idx: 0 for cls_idx, _ in enumerate(PLAYER_CLASSES)}
    for player_arrangement in permutations(range(len(PLAYER_CLASSES)), 4):
        players = [PLAYER_CLASSES[cls_idx](position) for position, cls_idx in enumerate(player_arrangement)]
        match_results = play_match(players, games_per_match)

        mprint("END OF MATCH", 1)
        mprint("Games won:", 1)
        mprint(match_results, 1)

        for match_idx, wins in enumerate(match_results):
            player_match_wins[player_arrangement[match_idx]] += wins

    return player_match_wins



PLAYER_CLASSES = [IdiotBot, IdiotBot, IdiotBot, IdiotBot]
tourney_results = play_tournament(games_per_match=5)

mprint("END OF TOURNAMENT", 1)
mprint("Results:", 1)
mprint(tourney_results, 1)
