"""
Allows players to launch a rocket.
To launch, need to press the right button while holding the grenade in hand.
Player gains 1 charge for every 8(configurable) kills or for capturing the flag/tent.
Also refills the player when receiving a rocket.

* ``/charge <player>`` to give player 1 rocket

Options
^^^^^^^

.. code-block:: toml
    [charge]
    color = [0, 0, 0]
    streak = 8
    # Grant 1 charge for capturing the flag 
    for_flag = true
    speed = 1.3

.. codeauthor:: Jipok
"""

from piqueserver.commands import command, admin, target_player, get_player
from pyspades.constants import BUILD_BLOCK, DESTROY_BLOCK, GRENADE_TOOL
from pyspades import world
from piqueserver.config import config
from pyspades.common import Vertex3, make_color
from pyspades.contained import BlockAction, GrenadePacket, SetColor


ROCKET_CONFIG = config.section('rocket')
ROCKET_COLOR = ROCKET_CONFIG.option('color', (0, 0, 0))
ROCKET_STREAK_REQUIREMENT = ROCKET_CONFIG.option('streak', 8)
ROCKET_FOR_FLAG = ROCKET_CONFIG.option('for_flag', True)
ROCKET_SPEED = ROCKET_CONFIG.option('speed', 1.3)

@command('rocket', admin_only=True)
def give_rocket(connection, player):
    player = get_player(connection.protocol, player)
    player.give_rocket()

class Rocket:
    pos = None
    ori = None
    player = None

def apply_script(protocol, connection, config):
    class RocketConnection(connection):

        def give_rocket(self):
            self.protocol.rocket_users_list.append(self)
            self.send_chat("You got the rocket. To use Right click with grenade")
            self.send_chat_notice("You got the rocket. To use Right click with grenade")
            self.protocol.send_chat("Warning: %s got a rocket!!!" % self.name)
            self.refill()

        def on_kill(self, killer, kill_type, grenade):
            if connection.on_kill(self, killer, kill_type, grenade) is False:
                return 
            if killer is None:
                return
            if not self in self.protocol.rocket_users_list:
                # don't increase streak if we have a strike on-hold
                if killer.streak and killer.streak % ROCKET_STREAK_REQUIREMENT.get() == 0:
                    killer.give_rocket()

        def on_flag_capture(self):
            if ROCKET_FOR_FLAG.get():
                self.give_rocket()
            connection.on_flag_capture(self)

        def boom(self, x, y, z):
            grenade_packet = GrenadePacket()
            grenade_packet.value = 0
            grenade_packet.player_id = self.player_id
            grenade_packet.position = (x, y, z)
            grenade_packet.velocity = (0, 0, 0)
            self.protocol.broadcast_contained(grenade_packet)
            self.protocol.world.create_object(
                world.Grenade, 0,
                Vertex3(x, y, z), None,
                Vertex3(0,0,0), self.grenade_exploded)

        def cast_rocket(self, pos, ori, start_boom = True):
            if pos.z <= -1:
                self.send_chat_error("Too high. Go down to launch a rocket")
                return False
            obj = Rocket()
            obj.pos = pos
            obj.ori = ori
            obj.player = self
            self.protocol.rockets.append(obj)
            set_color = SetColor()
            set_color.value = make_color(*ROCKET_COLOR.get())
            set_color.player_id = 32
            self.protocol.broadcast_contained(set_color)
            if start_boom:
                grenade_packet = GrenadePacket()
                grenade_packet.value = 0
                grenade_packet.player_id = self.player_id
                grenade_packet.position = self.world_object.position.get()
                grenade_packet.velocity = (0, 0, 0)
                self.protocol.broadcast_contained(grenade_packet)
            return True

        def on_secondary_fire_set(self, secondary):
            if secondary and self.tool == GRENADE_TOOL:
                if self in self.protocol.rocket_users_list or self.admin:
                    wo = self.world_object
                    if self.cast_rocket(wo.position.copy(), wo.orientation.copy()) and not self.admin:
                        self.protocol.rocket_users_list.remove(self)
                else:
                    self.send_chat_error("You have no rockets. Capture flag/tent or do %i kill streak" %
                                        ROCKET_STREAK_REQUIREMENT)
            connection.on_secondary_fire_set(self, secondary)

        def on_spawn(self, pos):
            if self in self.protocol.rocket_users_list:
                self.send_chat_warning("You have a rocket. To use Right click with grenade")
            return connection.on_spawn(self, pos)

    class RocketProtocol(protocol):
        rocket_users_list = []
        rockets = []

        def build_block(self, x, y, z):
            block_action = BlockAction()
            block_action.x = x
            block_action.y = y
            block_action.z = z
            block_action.player_id = 32
            block_action.value = BUILD_BLOCK
            self.broadcast_contained(block_action, save=True)

        def destroy_block(self, x, y, z):
            block_action = BlockAction()
            block_action.x = x
            block_action.y = y
            block_action.z = z
            block_action.player_id = 32
            block_action.value = DESTROY_BLOCK
            self.broadcast_contained(block_action, save=True) 

        def on_world_update(self):
            if self.loop_count % 1 == 0:
                for obj in self.rockets:
                    self.destroy_block(obj.pos.x, obj.pos.y, obj.pos.z)
                    obj.pos += obj.ori * ROCKET_SPEED.get()
                    solid = self.map.get_solid(obj.pos.x, obj.pos.y, obj.pos.z)
                    if solid or solid is None:
                        if solid:
                            for dx in range(-2, 3, 2):
                                for dy in range(-2, 3, 2):
                                    for dz in range(-2, 3, 2):
                                        obj.player.boom(obj.pos.x+dx, obj.pos.y+dy, obj.pos.z+dz)
                        self.rockets.remove(obj)
                        continue
                    self.build_block(obj.pos.x, obj.pos.y, obj.pos.z)
            return protocol.on_world_update(self)

    return RocketProtocol, RocketConnection
