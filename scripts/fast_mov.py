"""
Allows players to move faster several times.
By default, only administrators have this privilege.
Designed to simplify in-game debugging. 

* ``/fast <player>`` toggles the fast movement ability for the player 

.. codeauthor:: Jipok
"""

from piqueserver.commands import command, admin, get_player


@command('fast', admin_only=True)
def give_fast(connection, player=None, value=4):
    protocol = connection.protocol
    if player is not None:
        player = get_player(protocol, player)
    elif connection in protocol.players:
        player = connection
    else:
        raise ValueError()
    if player in protocol.accelerated:
        protocol.accelerated.remove(player)
        player.send_chat("You lost acceleration")
    else:
        protocol.accelerated.append(player)
        player.fast_mov_mul = float(value)
        player.send_chat("You are accelerated(" + str(value) + "x)")



def apply_script(protocol, connection, config):
    class FastMovementConnection(connection):
        up = False
        down = False
        left = False
        right = False
        fast_mov_mul = 4

        def on_walk_update(self, up: bool, down: bool, left: bool, right: bool) -> None:
            self.up = up
            self.down = down
            self.left = left
            self.right = right
            return connection.on_walk_update(self, up, down, left, right)

        def on_login(self, name):
            connection.on_login(self, name)
            if self.admin:
                give_fast(self, name)

        def on_disconnect(self):
            if self in self.protocol.accelerated:
                self.protocol.accelerated.remove(self)
            return connection.on_disconnect(self)


    class FastMovementProtocol(protocol):
        accelerated = []

        def on_world_update(self):
            for player in self.accelerated: # TODO fix spectators
                if player.up or player.down or player.left or player.right:
                    pos = player.world_object.position
                    vel = player.world_object.velocity
                    ox = player.world_object.orientation.x
                    oy = player.world_object.orientation.y
                    ox = ox*int(player.up) - ox*int(player.down)
                    oy = oy*int(player.up) - oy*int(player.down)
                    if player.right:
                        ox -= player.world_object.orientation.y
                        oy += player.world_object.orientation.x
                    if player.left:
                        ox += player.world_object.orientation.y
                        oy -= player.world_object.orientation.x
                    if abs(ox)+abs(oy) != 0:
                        dx = (ox/(abs(ox)+abs(oy)))*0.05*player.fast_mov_mul
                        dy = (oy/(abs(ox)+abs(oy)))*0.05*player.fast_mov_mul
                        if (self.map.get_solid(pos.x + dx, pos.y + dy, pos.z) == 0 and
                        self.map.get_solid(pos.x + dx, pos.y + dy, pos.z + 1) == 0 and
                        self.map.get_solid(pos.x + dx, pos.y + dy, pos.z + 2) == 0):
                            player.world_object.set_position(pos.x + dx, pos.y + dy, pos.z)
                            player.set_location()
            return protocol.on_world_update(self)

    return FastMovementProtocol, FastMovementConnection
