"""
For in-game debugging on a local machine only. 
Otherwise, players will experience twitching in the air.
By default every admin gets this.

Press ctrl(crouch) to move down
Press V(sneak) to move up
Press 4(grenade) for accelerate

* ``/fly <player>`` to toggle player ability to fly

.. codeauthor:: Jipok
"""

from piqueserver.commands import command, get_player
from pyspades.constants import GRENADE_TOOL
from twisted.internet.task import LoopingCall


#Movement multiplicator
FAST_MOV_MUL = 1.5


@command('fly', admin_only=True)
def give_fly(connection, player=None):
    protocol = connection.protocol
    if player is not None:
        player = get_player(protocol, player)
    elif connection in protocol.players:
        player = connection
    else:
        raise ValueError()
    if player in protocol.flying:
        protocol.flying.remove(player)
        player.send_chat("You are no longer flying")
    else:
        protocol.flying.append(player)
        player.send_chat("You are now flying")
        player.send_chat("Press ctrl(crouch) to move down")
        player.send_chat("Press V(sneak) to move up")
        player.send_chat("Press 4(grenade) for accelerate")


def apply_script(protocol, connection, config):
    class FlyConnection(connection):
        sneak = False
        crouch = False
        up = False
        down = False
        left = False
        right = False
        old_pos = None

        def on_walk_update(self, up: bool, down: bool, left: bool, right: bool) -> None:
            self.up = up
            self.down = down
            self.left = left
            self.right = right
            return connection.on_walk_update(self, up, down, left, right)

        def on_animation_update(self, jump, crouch, sneak, sprint):
            self.sneak = sneak
            self.crouch = crouch
            return connection.on_animation_update(self, jump, crouch, sneak, sprint)

        def on_fall(self, damage: int) -> bool:
            if self in self.protocol.flying:
                return False
            return connection.on_fall(self, damage)

        def on_login(self, name):
            connection.on_login(self, name)
            if self.admin:
                give_fly(self, name)

    class FlyProtocol(protocol):
        flying = []
        fly2_loop = None

        def fly_loop(self):
            for player in self.flying:
                if player.world_object is None:
                    continue
                pos = player.world_object.position
                vel = player.world_object.velocity
                ox = player.world_object.orientation.x
                oy = player.world_object.orientation.y
                ox = ox*int(player.up) - ox*int(player.down)
                oy = oy*int(player.up) - oy*int(player.down)
                if player.old_pos is None:
                    player.old_pos = pos.copy()
                dz = dx = dy = 0
                if player.right:
                    ox -= player.world_object.orientation.y
                    oy += player.world_object.orientation.x
                if player.left:
                    ox += player.world_object.orientation.y
                    oy -= player.world_object.orientation.x
                if player.sneak:
                    dz -= 0.06*FAST_MOV_MUL
                if player.crouch:
                    dz += 0.06*FAST_MOV_MUL
                if abs(ox)+abs(oy) != 0:
                    dx = (ox/(abs(ox)+abs(oy)))*0.05*FAST_MOV_MUL
                    dy = (oy/(abs(ox)+abs(oy)))*0.05*FAST_MOV_MUL
                if player.tool == GRENADE_TOOL:
                    dx *= 2.5
                    dy *= 2.5
                    dz *= 2
                if (self.map.get_solid(pos.x + dx, pos.y + dy, pos.z + dz) == 0 and
                self.map.get_solid(pos.x + dx, pos.y + dy, pos.z + dz + 1) == 0 and
                self.map.get_solid(pos.x + dx, pos.y + dy, pos.z + dz + 2) == 0):
                    player.old_pos.x += dx
                    player.old_pos.y += dy
                    player.old_pos.z += dz
                if (dz == 0) and self.map.get_solid(pos.x + dx, pos.y + dy, pos.z + dz + int(not player.crouch) + 2):
                    player.old_pos.z = pos.z
                pos = player.old_pos
                player.world_object.set_position(pos.x, pos.y, pos.z)
                if dx != 0 or dy !=0 or dz !=0 or (not self.map.get_solid(pos.x, pos.y, pos.z + int(not player.crouch) + 2)):
                    player.set_location()

        def on_map_change(self, map_):
            fly2_loop = LoopingCall(self.fly_loop)
            fly2_loop.start(1/180)
            return protocol.on_map_change(self, map_)

        def on_map_leave(self):
            if self.fly2_loop and self.fly2_loop.running:
                self.fly2_loop.stop()
            self.fly2_loop = None
            protocol.on_map_leave(self)

    return FlyProtocol, FlyConnection
