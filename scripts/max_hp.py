"""
Allows you to set the maximum hp for the player. 
It will automatically be filled with tents and when spawning.

* ``/max_hp <player> <new_max_hp>`` to change player's maximum hp

Options
^^^^^^^

.. code-block:: toml
    [max_hp]
    player_max_hp = 100
    show_non_default_hp = true

.. codeauthor:: Jipok
"""

from typing import Any, Optional, Sequence, Tuple, Union

from piqueserver.commands import command, admin, get_player
from pyspades.constants import FALL_KILL, WEAPON_KILL
from pyspades import world

from piqueserver.config import config
MAX_HP_CONFIG = config.section('max_hp')
PLAYER_MAX_HP = MAX_HP_CONFIG.option('player_max_hp', 100)
SHOW_HP = MAX_HP_CONFIG.option('show_non_default_hp', True)

from pyspades import contained as loaders
set_hp = loaders.SetHP()


@command('max_hp', admin_only=True)
def give_max_hp(connection, player=None, value=110):
    protocol = connection.protocol
    if player is not None:
        player = get_player(protocol, player)
    elif connection in protocol.players:
        player = connection
    else:
        raise ValueError()
    player.max_hp = int(value)
    player.set_hp(value)
    player.send_chat("Your maximum hp now: " + str(value))


def apply_script(protocol, connection, config):
    class MaxHpConnection(connection):
        max_hp = 100

        # Copied from the original method
        def set_hp(self, value: Union[int, float], hit_by: Optional['ServerConnection'] = None, kill_type: int = WEAPON_KILL,
               hit_indicator: Optional[Tuple[float, float, float]] = None, grenade: Optional[world.Grenade] = None) -> None:
            value = int(value)
            # Only the check for maximum health is changed here
            self.hp = max(0, min(self.max_hp, value))
            if self.hp <= 0:
                self.kill(hit_by, kill_type, grenade)
                return
            set_hp.hp = self.hp
            set_hp.not_fall = int(kill_type != FALL_KILL)
            if hit_indicator is None:
                if hit_by is not None and hit_by is not self:
                    hit_indicator = hit_by.world_object.position.get()
                else:
                    hit_indicator = (0, 0, 0)
            x, y, z = hit_indicator
            set_hp.source_x = x
            set_hp.source_y = y
            set_hp.source_z = z
            self.send_contained(set_hp)

            # Notify players if they shoot at player with an increased max_hp
            if SHOW_HP.get() and (hit_by is not None) and (hit_by is not self):
                if self.hp <= (self.max_hp - self.protocol.max_hp):
                    hit_by.send_chat(self.name + " hp: " + str(self.hp) + '/' + str(self.max_hp))


        def refill(self, local: bool = False) -> None:
            connection.refill(self, local)
            self.set_hp(self.max_hp)

        def on_spawn(self, pos):
            self.set_hp(self.max_hp)
            return connection.on_spawn(self, pos)

        def on_connect(self):
            self.max_hp = self.protocol.max_hp
            return connection.on_connect(self)


    class MaxHpProtocol(protocol):
        max_hp = 100

        def on_map_change(self, map):
            self.max_hp = PLAYER_MAX_HP.get()
            for player in self.players.values():
                player.max_hp = self.max_hp
            return protocol.on_map_change(self, map)

    return MaxHpProtocol, MaxHpConnection
