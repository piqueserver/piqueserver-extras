"""
Launches Armageddon after capturing the victory flag.
Armageddon is the fall of many rockets from the sky around the player who summoned it.
Requires script rocket.py by Jipok.

* ``/a`` Summons Armageddon. Admin Only

.. codeauthor:: Jipok
"""

from random import randrange

from piqueserver.commands import command, admin, target_player, get_player
from pyspades.common import Vertex3


@command('a', admin_only=True)
def call_armageddon(connection):
    protocol = connection.protocol
    player = connection
    pos = player.world_object.position
    protocol.armageddon_count = 60
    protocol.ax = pos.x
    protocol.ay = pos.y
    protocol.aplayer = player



def apply_script(protocol, connection, config):
    class ArmageddonConnection(connection):

        def cast_armageddon(self):
            print("ARMAGEDDON!!!!!!!!!!!!!!!!!!!!!")
            pos = self.world_object.position
            self.protocol.armageddon_count = 60
            self.protocol.ax = pos.x
            self.protocol.ay = pos.y
            self.protocol.aplayer = self

        def on_flag_capture(self):
            if max(self.team.score, self.team.other.score) == self.protocol.max_score:
                self.set_location_safe(self.team.other.get_random_location(True))
                self.cast_armageddon()
            connection.on_flag_capture(self)


    class ArmageddonProtocol(protocol):
        armageddon_count = 0
        ax = 0
        ay = 0
        aplayer = None

        def on_world_update(self):
            if self.armageddon_count and self.loop_count % 10 == 0:
                pos = Vertex3(self.ax + randrange(-30, 30), self.ay + randrange(-30, 30), 0)
                ori = Vertex3(randrange(-3, 3)/10, randrange(-3, 3)/10, 1)
                ori.normalize()
                self.aplayer.cast_rocket(pos, ori, False)        
                self.armageddon_count -= 1
            return protocol.on_world_update(self)

    return ArmageddonProtocol, ArmageddonConnection
