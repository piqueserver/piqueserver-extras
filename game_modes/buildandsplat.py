"""
buildandsplat by yvt - Clone of that popular game.

Win by painting as many blocks as possible with your team color.

Note: firing ink at someone deals a damage.
"""

# Copyright (c) 2016-2017 yvt.
#
# buildandsplat.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# buildandsplat.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with buildandsplat.py. If not, see <http://www.gnu.org/licenses/>.

from pyspades.server import Territory
from pyspades.common import Vertex3, make_color, get_color
from pyspades.constants import *
from piqueserver.commands import add, admin, get_player, name
from pyspades import contained as loaders
from pyspades.weapon import WEAPONS
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from pyspades import world
import math
import random

# Parameters for the Inknade
INKNADE_RAYS = 128
INKNADE_RANGE = 16.0
INKNADE_DROP_SIZE_MIN = 1
INKNADE_DROP_SIZE_MAX = 3

# Parameters for inkdamage (ink with the enemy color is splat when you took some damage)
INKDAMAGE_RAYS = 8
INKDAMAGE_RANGE = 16.0
INKDAMAGE_DROP_SIZE_MIN = 0
INKDAMAGE_DROP_SIZE_MAX = 1

HEAL_BY_FRIENDLY_FIRE = True

GLOBAL_STAT_INTERVAL = 20

INFINIINK = True

block_action = loaders.BlockAction()
change_weapon = loaders.ChangeWeapon()
set_color = loaders.SetColor()
progress_bar = loaders.ProgressBar()
move_object = loaders.MoveObject()
restock = loaders.Restock()

# weapon parameters taken from OS
weapon_trajectory_param = {
    RIFLE_WEAPON : {
        'spread': 0.006,
        'num_pellets': 1,
        'range': 128.0,
        'drop_size': 3
    },
    SMG_WEAPON : {
        'spread': 0.012,
        'num_pellets': 1,
        'range': 128.0,
        'drop_size': 2
    },
    SHOTGUN_WEAPON : {
        'spread': 0.08, # more than actual value, but more spread is more fun!
        'num_pellets': 8,
        'range': 40.0,
        'drop_size': 2
    }
}

drop_points_list = []
for size in range(0, 4):
    drop_points = []
    for dx in range(-size, size + 1):
        for dy in range(-size, size + 1):
            for dz in range(-size, size + 1):
                if abs(dx) + abs(dy) + abs(dz) <= size:
                    drop_points.append((dx, dy, dz))
    drop_points_list.append(drop_points)

# fire ink when a weapon was fired
def apply_splatgun(weapon):
    class Splatgun(weapon):
        def __init__(self, fire_callback, *args, **kargs):
            self.shoot_call = None
            self.fire_callback = fire_callback
            weapon.__init__(self, *args, **kargs)

        def reset(self):
            if self.shoot_call is not None:
                self.shoot_call.cancel()
                self.shoot_call = None
            weapon.reset(self)

        def set_shoot(self, value):
            old_shoot = self.shoot
            ammo = self.get_ammo(True)
            weapon.set_shoot(self, value)
            if self.shoot and not old_shoot:
                self.real_current_ammo = ammo
                self.real_shoot_time = self.shoot_time
                self.shoot_call = reactor.callLater(max(self.real_shoot_time - reactor.seconds(), 0), self.on_fired)
            elif not self.shoot:
                if self.shoot_call is not None:
                    self.shoot_call.cancel()
                    self.shoot_call = None

        def generate_bullet_direction(self, player_orientation):
            orient = player_orientation.copy()
            orient.normalize()
            ret = []
            params = weapon_trajectory_param[weapon.id]
            num_pellets = params['num_pellets']
            spread = params['spread']

            for i in range(0, num_pellets):
                orient.x += (random.random() - random.random()) * spread
                orient.y += (random.random() - random.random()) * spread
                orient.z += (random.random() - random.random()) * spread
                ret.append(orient.copy())

            return ret

        def on_fired(self):
            self.shoot_call = None
            if self.real_current_ammo <= 0 or not self.shoot:
                return
            self.real_shoot_time += self.delay

            # make sure on_fired is not called too many times in case
            # the server became unresponsive for the certain period.
            while self.real_shoot_time < reactor.seconds():
                self.real_shoot_time += self.delay
                self.real_current_ammo -= 1

            self.shoot_call = reactor.callLater(max(self.real_shoot_time - reactor.seconds(), 0), self.on_fired)
            self.real_current_ammo -= 1

            # callback
            self.fire_callback()
    return Splatgun

for weap_id, weapon in WEAPONS.items():
    WEAPONS[weap_id] = apply_splatgun(weapon)

# blend function
nonlinearize_map = [int(math.sqrt(i) + 0.5) for i in range(0, 255 * 255 + 1)]
def blend_color_single(a, b, p):
    a *= a; b *= b
    v = a * (256 - p) + b * p + 128
    return nonlinearize_map[v >> 8]

def blend_color(a, b, p):
    r1, g1, b1 = a
    r2, g2, b2 = b
    r = blend_color_single(r1, r2, p)
    g = blend_color_single(g1, g2, p)
    b = blend_color_single(b1, b2, p)
    return r, g, b

@name('stat')
def show_stat(connection):
    protocol = connection.protocol
    msg = protocol.get_stat_message()
    connection.send_chat(msg)
add(show_stat)

def apply_script(protocol, connection, config):
    class BuildAndSplatConnection(connection):
        def get_spawn_location(self):
            # don't want spawn location decided using territory location
            self.protocol.game_mode = CTF_MODE
            p = connection.get_spawn_location(self)
            self.protocol.game_mode = TC_MODE
            return p

        def set_weapon(self, weapon, local = False, no_kill = False):
            self.weapon = weapon
            if self.weapon_object is not None:
                self.weapon_object.reset()
            self.weapon_object = WEAPONS[weapon](self._on_fire, self._on_reload)
            if not local:
                self.protocol.send_contained(change_weapon, save = True)
                if not no_kill:
                    self.kill(type = CLASS_CHANGE_KILL)

        def _on_fire(self):
            if self.team is not None and self.world_object is not None:
                bullets = self.weapon_object.generate_bullet_direction(self.world_object.orientation)
                params = weapon_trajectory_param[self.weapon_object.id]
                weapon_range = params['range']

                pts = []
                for bullet in bullets:

                    dummy_character = world.Character(self.world_object.world, self.world_object.position, bullet)

                    loc = dummy_character.cast_ray(weapon_range * 2.0)
                    if loc:
                        x, y, z = loc
                        if (Vertex3(x, y, z) - self.world_object.position).length_sqr() > weapon_range*weapon_range:
                            # out of range
                            continue
                        pts.append((x, y, z))
                self.protocol.paint_block_by_team_splat(self, pts, self.team, params['drop_size'])

        def on_block_build_attempt(self, x, y, z):

            # make sure block is built with the team color
            if self.team is not None:
                brightness = random.randint(180, 255)
                self.color = (
                    self.team.color[0] * brightness >> 8,
                    self.team.color[1] * brightness >> 8,
                    self.team.color[2] * brightness >> 8
                )
                set_color.player_id = self.player_id
                set_color.value = make_color(*self.color)
                self.protocol.send_contained(set_color, sender=None, save=True)

            return connection.on_block_build_attempt(self, x, y, z)

        def on_block_build(self, x, y, z):

            # check owner
            if self.team is not None:
                self.protocol.territory_map.own(x, y, z, self.team.id + 1)

            # if some blocks were completely covered by the new one, it's no longer owned
            m = self.protocol.map
            for dx, dy, dz in [
                (-1, 0, 0),
                (1, 0, 0),
                (0, -1, 0),
                (0, 1, 0),
                (0, 0, -1),
                (0, 0, 1)
            ]:
                if not m.is_surface(x+dx, y+dy, z+dz):
                    self.protocol.territory_map.own(x+dx, y+dy, z+dz, 0)

            return connection.on_block_build(self, x, y, z)

        def on_block_destroy(self, x, y, z, mode):
            if mode == DESTROY_BLOCK:
                # block cannot be harmed by weapon because weapons are all splatguns!
                if self.tool == WEAPON_TOOL:
                    return False
            elif mode == GRENADE_DESTROY:
                return False
            return connection.on_block_destroy(self, x, y, z, mode)

        def on_block_removed(self, x, y, z):
            self.protocol.territory_map.own(x, y, z, 0)

            return connection.on_block_removed(self, x, y, z)

        def _on_reload(self):
            if INFINIINK:
                self.weapon_object.restock()
                # self.send_contained(restock)
            connection._on_reload(self)

        def grenade_exploded(self, grenade):
            # inknade

            if self.team is not None:
                # adjust position
                pos = grenade.position.copy()
                mp = self.protocol.map

                for i in range(0, 1):
                    if mp.get_solid(int(pos.x), int(pos.y), int(pos.z)) or \
                        mp.get_solid(int(pos.x), int(pos.y), int(pos.z) - 1) or \
                        mp.get_solid(int(pos.x), int(pos.y), int(pos.z) - 2):
                        break
                    pos.z -= 1.0

                pts = []

                for i in range(0, INKNADE_RAYS):
                    orient = Vertex3(random.gauss(0.0, 1.0), random.gauss(0.0, 1.0), random.gauss(0.0, 1.0))
                    orient.normalize()
                    dummy_character = world.Character(grenade.world, pos, orient)

                    loc = dummy_character.cast_ray(INKNADE_RANGE * 2.0)
                    if loc:
                        x, y, z = loc
                        if (Vertex3(x, y, z) - pos).length_sqr() > INKNADE_RANGE*INKNADE_RANGE:
                            # out of range
                            continue
                        pts.append((x, y, z))
                self.protocol.paint_block_by_team_splat(self, pts, self.team, random.randint(INKNADE_DROP_SIZE_MIN, INKNADE_DROP_SIZE_MAX))

            return connection.grenade_exploded(self, grenade)

        def on_hit(self, hit_amount, hit_player, type, grenade):
            if self != hit_player and type in [WEAPON_KILL, HEADSHOT_KILL] and self.team is not None:
                # inkdamage
                pos = hit_player.world_object.position
                pts = []
                for i in range(0, INKDAMAGE_RAYS):
                    orient = Vertex3(random.gauss(0.0, 1.0), random.gauss(0.0, 1.0), random.gauss(0.0, 1.0))
                    orient.normalize()
                    dummy_character = world.Character(self.world_object.world, pos, orient)

                    loc = dummy_character.cast_ray(INKDAMAGE_RANGE * 2.0)
                    if loc:
                        x, y, z = loc
                        if (Vertex3(x, y, z) - pos).length_sqr() > INKDAMAGE_RANGE*INKDAMAGE_RANGE:
                            # out of range
                            continue
                        pts.append((x, y, z))
                self.protocol.paint_block_by_team_splat(self, pts, self.team, random.randint(INKDAMAGE_DROP_SIZE_MIN, INKDAMAGE_DROP_SIZE_MAX))

                # heal
                if HEAL_BY_FRIENDLY_FIRE and self.team == hit_player.team:
                    if hit_player.hp < 100:
                        hit_player.set_hp(min(hit_player.hp + hit_amount, 100))
                        hit_player.send_chat("N%% You were healed by %s" % hit_player.name)
                    return False

            return connection.on_hit(self, hit_amount, hit_player, type, grenade)

    def _territory_map_compute_index(x, y, z):
        return x | (y << 9) | (z << 18)

    class TerritoryMap:
        # cell value
        #  0 -- neutral
        #  1 -- team 1
        #  2 -- team 2

        def __init__(self):
            self.count = [0, 0, 0]
            self.map = {}
            return
        def own(self, x, y, z, new_owner):
            if new_owner < 0 or new_owner >= 4:
                raise RuntimeError("bad owner")

            index = _territory_map_compute_index(x, y, z)
            large_index = index >> 4
            small_index = (index & 0xf) << 1

            cell = self.map.get(large_index, 0)

            owner = (cell >> small_index) & 3
            if owner == new_owner:
                return False

            self.count[owner] -= 1
            self.count[new_owner] += 1

            cell = (cell & ~(3 << small_index)) | (new_owner << small_index)
            self.map[large_index] = cell

            return True

        def get_score(self, team):
            return self.count[team]

    class SplatgaugeTerritory(Territory):
        def __init__(self, protocol):
            Territory.__init__(self, 0, protocol, 0, 0, 0)
            self.check_rate_loop = LoopingCall(self.update_rate)
            self.check_rate_loop.start(0.2)

        def delete(self, *arg, **kw):
            self.check_rate_loop.stop()
            return Territory.delete(self, *arg, **kw)

        def add_player(self, player):
            # not actually Territory. just ignore.
            pass
        def remove_player(self, player):
            # not actually Territory. just ignore.
            pass
        def update(self):
            if self.team is None:
                return
            move_object.object_type = self.id
            move_object.state = self.team.id

            # follow players
            for player in list(self.protocol.connections.values()):
                if player.world_object is None:
                    continue
                pos = player.world_object.position - player.world_object.orientation * 10
                move_object.x = pos.x
                move_object.y = pos.y
                move_object.z = pos.z
                player.send_contained(move_object)

        def update_rate(self):
            score1 = self.protocol.territory_map.get_score(1)
            score2 = self.protocol.territory_map.get_score(2)

            # add some bias when territory is too small
            bias = max(0, 10 - max(score1, score2))
            score1 += bias; score2 += bias

            per = float(score1) / (score1 + score2)

            progress_bar.object_index = self.id
            if score1 >= score2:
                progress_bar.capturing_team = 1
                progress_bar.progress = 1 - per
                self.team = self.protocol.teams[0]
            else:
                progress_bar.capturing_team = 0
                progress_bar.progress = per
                self.team = self.protocol.teams[1]
            progress_bar.rate = 0
            self.protocol.send_contained(progress_bar)

            self.update()



    class BuildAndSplatProtocol(protocol):
        game_mode = TC_MODE

        def on_map_change(self, map):
            self.territory_map = TerritoryMap()

            self.check_destroy_spans = set()
            self.check_destroy_spans_list = []
            self.check_destroy_span_index = 0
            self.check_destroy_loop = LoopingCall(self.check_destroy)
            self.check_destroy_loop.start(0.1)

            if GLOBAL_STAT_INTERVAL > 0:
                self.report_loop = LoopingCall(self.report_stat)
                self.report_loop.start(GLOBAL_STAT_INTERVAL)
            else:
                self.report_loop = None

            protocol.on_map_change(self, map)

        def on_map_leave(self):
            if self.check_destroy_loop and self.check_destroy_loop.running:
                self.check_destroy_loop.stop()
            if self.report_loop and self.report_loop.running:
                self.report_loop.stop()
            protocol.on_map_leave(self)

        def _time_up(self):
            score1 = self.territory_map.get_score(1)
            score2 = self.territory_map.get_score(2)

            self.advance_call = None

            if score1 != score2:
                self.reset_game(territory=self.splat_territory)
                self.on_game_end()
            else:
                self.on_game_end()


        def check_destroy(self):
            # fallen block cannot be detected by member method.
            # we have to somehow detect them.
            if len(self.check_destroy_spans_list) == 0:
                # no territory
                return

            start_idx = self.check_destroy_span_index
            for i in range(0, 100):
                (x, y) = self.check_destroy_spans_list[self.check_destroy_span_index]

                for z in range(0, 64):
                    if not self.map.get_solid(x, y, z):
                        self.territory_map.own(x, y, z, 0)

                self.check_destroy_span_index += 1

                if self.check_destroy_span_index == len(self.check_destroy_spans_list):
                    self.check_destroy_span_index = 0

                if self.check_destroy_span_index == start_idx:
                    break

        def get_cp_entities(self):
            self.splat_territory = SplatgaugeTerritory(self)
            return [self.splat_territory]

        def get_stat_message(self):
            mp = self.territory_map

            names = [self.teams[0].name, self.teams[1].name]
            scores = [mp.get_score(1), mp.get_score(2)]

            if scores[0] > scores[1]:
                leads = "%s leads!" % names[0]
            elif scores[0] < scores[1]:
                leads = "%s leads!" % names[1]
            else:
                leads = "draw"

            return "N%% %s: %d - %s: %d (%s)" % (names[0], scores[0], names[1], scores[1], leads)

        def get_mode_name(self):
            return "splat"

        def report_stat(self):
            self.send_chat(self.get_stat_message())

        def paint_block_by_team_splat(self, player, in_points, team, rng):
            if len(in_points) == 0:
                return
            pts = []
            mp = self.map
            for x, y, z in in_points:
                for dx, dy, dz in drop_points_list[rng]:
                    sx = x + dx; sy = y + dy; sz = z + dz
                    pts.append((sx, sy, sz))
                    if mp.get_solid(sx - 1, sy, sz) and mp.get_solid(sx + 1, sy, sz) and mp.is_surface(sx - 1, sy, sz) and mp.is_surface(sx + 1, sy, sz):
                        sx += random.randint(-1,1)
                    if mp.get_solid(sx, sy - 1, sz) and mp.get_solid(sx, sy + 1, sz) and mp.is_surface(sx, sy - 1, sz) and mp.is_surface(sx, sy + 1, sz):
                        sy += random.randint(-1,1)
                    if mp.get_solid(sx, sy, sz - 1) and mp.get_solid(sx, sy, sz + 1) and mp.is_surface(sx, sy, sz - 1) and mp.is_surface(sx, sy, sz + 1):
                        sz += random.randint(-1,1)
                    pts.append((sx, sy, sz))
            self.paint_block_by_team(player, pts, team)

        def paint_block_by_team(self, player, points, team):
            updated_points = set()
            for x, y, z in points:
                if x < 0 or y < 0 or z < 0 or x >= 512 or y >= 512 or z >= 63:
                    continue

                # empty?
                if not self.map.get_solid(x, y, z) or not self.map.is_surface(x, y, z):
                    continue

                # already owned?
                if not self.territory_map.own(x, y, z, team.id + 1):
                    pass # return False

                updated_points.add((x, y, z))

                color = self.map.get_color(x, y, z)

                color = blend_color(color, team.color, random.randint(160,200))

                self.map.set_point(x, y, z, color)

            for x, y, z in updated_points:
                color = self.map.get_color(x, y, z)

                player.color = color
                set_color.player_id = player.player_id
                set_color.value = make_color(*color)
                self.send_contained(set_color, sender=None, save=True)

                block_action.x = x
                block_action.y = y
                block_action.z = z
                block_action.player_id = player.player_id
                block_action.value = DESTROY_BLOCK
                self.send_contained(block_action, save = True)
                block_action.value = BUILD_BLOCK
                self.send_contained(block_action, save = True)

                if (x, y) not in self.check_destroy_spans:
                    self.check_destroy_spans.add((x, y))
                    self.check_destroy_spans_list.append((x, y))


    return BuildAndSplatProtocol, BuildAndSplatConnection