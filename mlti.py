
import asyncio
import json
import queue
import sys
import threading

import websockets
from PyQt5.QtCore import Qt, QTimer,QPoint
from PyQt5.QtGui import QFont, QPainter,QColor,QPolygon
from PyQt5.QtWidgets import QComboBox



from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QColorDialog,
    QComboBox,
    )


SERVER_ADDRESS = "ws://192.168.1.49:8765"
#SERVER_ADDRESS = "ws://10.121.249.0:8765"  # School




class SettingsWindow(QWidget):
    def __init__(self, game):
        super().__init__()

        self.game = game

        self.setWindowTitle("Settings")
        self.resize(300, 200)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Player Name:"))

        self.name_input = QLineEdit()
        self.name_input.setText(self.game.player_name)
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Player Shape:"))
        self.shape_box = QComboBox()
        self.shape_box.addItems(["circle", "square", "triangle", "star"])
        self.shape_box.setCurrentText(self.game.player_shape)
        layout.addWidget(self.shape_box)


        # Color picker button
        color_button = QPushButton("Choose Color")
        color_button.clicked.connect(self.choose_color)
        layout.addWidget(color_button)
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_name)
        layout.addWidget(save_button)
        self.setLayout(layout)

        layout.addWidget(QLabel("Cosmetic:"))

        self.cosmetic_box = QComboBox()
        self.cosmetic_box.addItems(self.game.cosmetics_unlocked)
        self.cosmetic_box.setCurrentText(self.game.cosmetic_equipped)
        layout.addWidget(self.cosmetic_box)


    def choose_color(self):
        color = QColorDialog.getColor()

        if color.isValid():
            self.game.player_color = color

            if self.game.ws:
                self.game.outgoing.put({
                    "type": "set_color",
                    "color": color.name()
                })

    def save_name(self):
        new_name = self.name_input.text().strip()

        if new_name:
            self.game.player_name = new_name

            if self.game.ws:
                self.game.outgoing.put({
                    "type": "set_name",
                    "name": new_name,
                })
        new_shape = self.shape_box.currentText()
        self.game.player_shape = new_shape

        if self.game.ws:
            self.game.outgoing.put({
                "type": "set_shape",
                "shape": new_shape
            })
        chosen_cosmetic = self.cosmetic_box.currentText()
        self.game.cosmetic_equipped = chosen_cosmetic

        if self.game.ws:
            self.game.outgoing.put({
                "type": "equip_cosmetic",
                "cosmetic": chosen_cosmetic
            })



        self.close()




class Game(QWidget):
    def __init__(self):
        super().__init__()

        # ---------------- WINDOW ----------------
        self.setWindowTitle("Multiplayer Template")
        self.resize(1900, 1100)
        self.setMouseTracking(True)

        self.game_mode = "ffa"
        self.vote_timer = 120      # 2 minutes voting
        self.game_timer = 300      # 5 minutes match

        self.ffa_votes = 0
        self.team_votes = 0

        self.state = "lobby"   # "lobby" or "game"

        # ---------------- PLAYER ----------------
        self.player_id = None
        self.is_host = False

        self.player_name = "Guest"

        self.player_x = 400
        self.player_y = 300
        self.player_health = 100
        self.speed = 5
        self.player_color = Qt.green
        self.player_shape = "circle"   # default
        self.cosmetics_unlocked = ["none"]
        self.cosmetic_equipped = "none"

        # ---------------- LOBBY ----------------
        # Use a dict: {player_id: name}
        self.lobby_players = {}

        # ---------------- PLAYERS ----------------
        self.other_players = {}

        # ---------------- PROJECTILES ----------------
        self.projectiles = []

        # ---------------- CHAT ----------------
        self.chat_messages = []
        self.max_chat_messages = 8
        self.current_chat_input = ""
        self.typing_chat = False

        # ---------------- MOVEMENT ----------------
        self.move_up = False
        self.move_down = False
        self.move_left = False
        self.move_right = False

        # ---------------- MOUSE ----------------
        self.mouse_x = 0
        self.mouse_y = 0

        # ---------------- NETWORKING ----------------
        self.ws = None
        self.outgoing = queue.Queue()

        # ---------------- GAME STATE ----------------
        self.game_started = False

        # ---------------- TIMER ----------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.game_update)
        self.timer.start(16)  # Approximately 60 FPS

        # ---------------- NETWORK THREAD ----------------
        threading.Thread(
            target=self.start_network,
            daemon=True,
        ).start()

    # =========================================================
    # CHAT
    # =========================================================

    def send_chat(self, text):
        if self.ws:
            self.outgoing.put(
                {
                    "type": "chat",
                    "message": text,
                }
            )

    def add_chat_message(self, message):
        self.chat_messages.append(message)

        if len(self.chat_messages) > self.max_chat_messages:
            self.chat_messages.pop(0)

        self.update()

    # =========================================================
    # LOBBY
    # =========================================================

    def start_game_window(self):
        self.game_started = True
        self.show()

    # =========================================================
    # NETWORKING
    # =========================================================

    def start_network(self):
        asyncio.run(self.network_loop())

    async def network_loop(self):
        try:
            async with websockets.connect(SERVER_ADDRESS) as ws:
                self.ws = ws

                # Send player name when connecting
                await ws.send(
                    json.dumps(
                        {
                            "type": "set_name",
                            "name": self.player_name,
                        }
                    )
                )

                while True:
                    # ---------------- SEND QUEUED MESSAGES ----------------
                    while not self.outgoing.empty():
                        message = self.outgoing.get()
                        await ws.send(json.dumps(message))

                    # ---------------- RECEIVE SERVER DATA ----------------
                    try:
                        message = await ws.recv()
                    except websockets.ConnectionClosed:
                        print("Disconnected from server.")
                        break

                    data = json.loads(message)
                    message_type = data.get("type")

                    # ---------------- WELCOME ----------------
                    if message_type == "welcome":
                        self.player_id = data["id"]
                        continue

                    # ---------------- GAME START / END ----------------
                 
                    if message_type == "game_start":
                        self.state = "game"
                        self.vote_timer = 120
                        self.game_timer = 300
                        continue

                    if message_type == "game_end":
                        self.state = "lobby"
                        self.vote_timer = 120
                        self.game_timer = 300
                        self.game_mode = "ffa"
                        self.ffa_votes = 0
                        self.team_votes = 0
                        continue

                    # ---------------- LOBBY UPDATE ----------------
                    if message_type == "lobby_update":
                        # Expect: {"players": {id: name}}
                        self.lobby_players = data["players"]
                        continue

                    # ---------------- HOST UPDATE ----------------
                    if message_type == "host_update":
                        self.is_host = (data["host_id"] == self.player_id)
                        continue

                    # ---------------- KILL FEED ----------------
                    if message_type == "kill":
                        kill_message = (
                            f"{data['killer']} eliminated "
                            f"{data['victim']} "
                            f"({data['kills']} kills)"
                        )
                        self.add_chat_message(kill_message)
                        continue

                    # ---------------- COSMETIC UNLOCK ----------------
                    if message_type == "cosmetic_unlock":
                        new_cosmetic = data["cosmetic"]
                        if new_cosmetic not in self.cosmetics_unlocked:
                            self.cosmetics_unlocked.append(new_cosmetic)
                        self.add_chat_message(f"Unlocked cosmetic: {new_cosmetic}")
                        continue

                    # ---------------- CHAT ----------------
                    if message_type == "chat":
                        chat_message = f"{data['name']}: {data['message']}"
                        self.add_chat_message(chat_message)
                        continue

                    # ---------------- GAME MODE UPDATE ----------------
                    if message_type == "game_mode_update":
                        self.game_mode = data["mode"]
                        self.ffa_votes = data["ffa_votes"]
                        self.team_votes = data["team_votes"]
                        continue

                    # ---------------- GAME STATE ----------------
                    if "players" in data:
                        self.other_players = data["players"]

                        # Update our own player information
                        if self.player_id is not None:
                            player_data = self.other_players.get(
                                str(self.player_id),
                                self.other_players.get(self.player_id),
                            )
                            if player_data:
                                self.player_health = player_data.get(
                                    "health",
                                    self.player_health,
                                )
                                self.player_color = QColor(
                                    player_data.get("color", "#00ff00")
                                )
                                self.player_shape = player_data.get(
                                    "shape",
                                    self.player_shape,
                                )
                                self.cosmetic_equipped = player_data.get(
                                    "cosmetic",
                                    self.cosmetic_equipped,
                                )

                    if "projectiles" in data:
                        self.projectiles = data["projectiles"]

                    self.update()

        except Exception as error:
            print("Network error:", error)

        finally:
            self.ws = None

    # =========================================================
    # GAME LOGIC
    # =========================================================

    def game_update(self):
        # ---------------- MOVEMENT ----------------
        if self.move_up:
            self.player_y -= self.speed

        if self.move_down:
            self.player_y += self.speed

        if self.move_left:
            self.player_x -= self.speed

        if self.move_right:
            self.player_x += self.speed

        # Voting timer
        if self.state == "lobby":
            self.vote_timer -= 0.016
            if self.vote_timer <= 0:
                # Voting finished, wait for server to send game_start
                self.vote_timer = 0

        # Game timer
        if self.state == "game":
            self.game_timer -= 0.016
            if self.game_timer <= 0:
                self.game_timer = 0
                # Server will send game_end automatically

        # ---------------- SEND POSITION ----------------
        if self.ws and self.state == "game":
            self.outgoing.put(
                {
                    "type": "move",
                    "x": self.player_x,
                    "y": self.player_y,
                }
            )

        self.update()

    # =========================================================
    # DRAWING
    # =========================================================

    def paintEvent(self, event):
        painter = QPainter(self)

        # Background
        if self.state == "lobby":
            painter.fillRect(self.rect(), Qt.black)
        else:
            painter.fillRect(self.rect(), Qt.red)

        painter.setFont(QFont("Arial", 12))

        # ---------------- DRAW SELF ----------------
        painter.setBrush(self.player_color)

        if self.player_shape == "circle":
            painter.drawEllipse(self.player_x - 15, self.player_y - 15, 30, 30)

        elif self.player_shape == "square":
            painter.drawRect(self.player_x - 15, self.player_y - 15, 30, 30)

        elif self.player_shape == "triangle":
            points = [
                QPoint(self.player_x, self.player_y - 20),
                QPoint(self.player_x - 20, self.player_y + 20),
                QPoint(self.player_x + 20, self.player_y + 20),
            ]
            painter.drawPolygon(QPolygon(points))

        elif self.player_shape == "star":
            points = [
                QPoint(self.player_x, self.player_y - 20),
                QPoint(self.player_x - 6, self.player_y - 6),
                QPoint(self.player_x - 20, self.player_y - 6),
                QPoint(self.player_x - 10, self.player_y + 6),
                QPoint(self.player_x - 14, self.player_y + 20),
                QPoint(self.player_x, self.player_y + 10),
                QPoint(self.player_x + 14, self.player_y + 20),
                QPoint(self.player_x + 10, self.player_y + 6),
                QPoint(self.player_x + 20, self.player_y - 6),
                QPoint(self.player_x + 6, self.player_y - 6),
            ]
            painter.drawPolygon(QPolygon(points))

        painter.drawText(
            self.player_x - 20,
            self.player_y - 25,
            self.player_name,
        )

        self.draw_health_bar(
            painter,
            self.player_x,
            self.player_y,
            self.player_health,
        )

        if self.cosmetic_equipped == "hat_basic":
            painter.setBrush(Qt.yellow)
            painter.drawRect(self.player_x - 15, self.player_y - 35, 30, 10)

        # ---------------- DRAW OTHER PLAYERS ----------------
        for player_id, player in self.other_players.items():
            if str(player_id) == str(self.player_id):
                continue

            x = player["x"]
            y = player["y"]

            painter.setBrush(QColor(player.get("color", "#0000ff")))
            shape = player.get("shape", "circle")

            if shape == "circle":
                painter.drawEllipse(x - 15, y - 15, 30, 30)

            elif shape == "square":
                painter.drawRect(x - 15, y - 15, 30, 30)

            elif shape == "triangle":
                points = [
                    QPoint(x, y - 20),
                    QPoint(x - 20, y + 20),
                    QPoint(x + 20, y + 20),
                ]
                painter.drawPolygon(QPolygon(points))

            elif shape == "star":
                points = [
                    QPoint(x, y - 20),
                    QPoint(x - 6, y - 6),
                    QPoint(x - 20, y - 6),
                    QPoint(x - 10, y + 6),
                    QPoint(x - 14, y + 20),
                    QPoint(x, y + 10),
                    QPoint(x + 14, y + 20),
                    QPoint(x + 10, y + 6),
                    QPoint(x + 20, y - 6),
                    QPoint(x + 6, y - 6),
                ]
                painter.drawPolygon(QPolygon(points))

            painter.drawText(
                x - 20,
                y - 25,
                player["name"],
            )

            self.draw_health_bar(
                painter,
                x,
                y,
                player.get("health", 100),
            )

            cosmetic = player.get("cosmetic", "none")
            if cosmetic == "hat_basic":
                painter.setBrush(Qt.yellow)
                painter.drawRect(x - 15, y - 35, 30, 10)

        # ---------------- DRAW PROJECTILES ----------------
        painter.setBrush(Qt.red)

        for projectile in self.projectiles:
            x = int(projectile["x"])
            y = int(projectile["y"])

            painter.drawEllipse(
                x - 5,
                y - 5,
                10,
                10,
            )

        # ---------------- DRAW CHAT ----------------
        painter.setPen(Qt.white)
        painter.setFont(QFont("Arial", 14))

        y = self.height() - 150

        for message in self.chat_messages:
            painter.drawText(
                20,
                y,
                message,
            )
            y += 20

        # ---------------- CHAT INPUT ----------------
        if self.typing_chat:
            painter.drawText(
                20,
                self.height() - 20,
                "> " + self.current_chat_input,
            )

        # ---------------- LOBBY UI ----------------
        if self.state == "lobby":
            painter.drawText(500, 50, "Lobby - Waiting for players...")
            painter.drawText(50, 50, f"Voting ends in: {int(self.vote_timer)}s")
            painter.drawText(50, 80, "Vote Game Mode")

            # FFA vote button
            painter.drawRect(50, 100, 200, 50)
            painter.drawText(80, 130, f"FFA ({self.ffa_votes} votes)")

            # Teams vote button
            painter.drawRect(50, 170, 200, 50)
            painter.drawText(80, 200, f"Teams ({self.team_votes} votes)")

            # Show current mode
            painter.drawText(50, 260, f"Current Mode: {self.game_mode}")

            # Lobby player list
            y = 300
            for pid, name in self.lobby_players.items():
                painter.drawText(50, y, f"- {name}")
                y += 30

        # ---------------- GAME TIMER ----------------
        if self.state == "game":
            painter.drawText(50, 50, f"Match ends in: {int(self.game_timer)}s")

    def draw_health_bar(self, painter, x, y, health):
        health = max(0, min(100, health))

        # Background
        painter.setBrush(Qt.red)
        painter.drawRect(
            x - 20,
            y + 10,
            40,
            5,
        )

        # Health
        painter.setBrush(Qt.green)

        health_width = int(40 * (health / 100))

        painter.drawRect(
            x - 20,
            y + 10,
            health_width,
            5,
        )

    # =========================================================
    # MOUSE INPUT
    # =========================================================

    def mouseMoveEvent(self, event):
        self.mouse_x = event.x()
        self.mouse_y = event.y()

    def mousePressEvent(self, event):
        # Player selects team
        if self.state == "lobby" and self.game_mode == "teams":
            # Red team
            if 300 <= event.x() <= 450 and 290 <= event.y() <= 330:
                self.outgoing.put({"type": "set_team", "team": "red"})
                return

            # Blue team
            if 300 <= event.x() <= 450 and 340 <= event.y() <= 380:
                self.outgoing.put({"type": "set_team", "team": "blue"})
                return

        if self.state == "lobby":
            # Vote FFA
            if 50 <= event.x() <= 250 and 100 <= event.y() <= 150:
                self.outgoing.put({"type": "vote_game_mode", "mode": "ffa"})
                return

            # Vote Teams
            if 50 <= event.x() <= 250 and 170 <= event.y() <= 220:
                self.outgoing.put({"type": "vote_game_mode", "mode": "teams"})
                return

        self.shoot()

    # =========================================================
    # KEYBOARD INPUT
    # =========================================================

    def keyPressEvent(self, event):
        # ---------------- MOVEMENT ----------------
        if event.key() == Qt.Key_W:
            self.move_up = True
            return

        if event.key() == Qt.Key_S:
            self.move_down = True
            return

        if event.key() == Qt.Key_A:
            self.move_left = True
            return

        if event.key() == Qt.Key_D:
            self.move_right = True
            return

        # ---------------- SHOOT ----------------
        if event.key() == Qt.Key_Space:
            self.shoot()
            return

        # ---------------- CHAT ----------------
        if event.key() == Qt.Key_Return:
            self.handle_chat_enter()
            return

        # ---------------- SETTINGS ----------------
        if event.key() == Qt.Key_Escape:
            self.settings = SettingsWindow(self)
            self.settings.show()
            return

        # ---------------- CHAT TYPING ----------------
        if self.typing_chat:
            if event.key() == Qt.Key_Backspace:
                self.current_chat_input = self.current_chat_input[:-1]
            else:
                character = event.text()
                if character and character.isprintable():
                    self.current_chat_input += character

            self.update()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_W:
            self.move_up = False
        elif event.key() == Qt.Key_S:
            self.move_down = False
        elif event.key() == Qt.Key_A:
            self.move_left = False
        elif event.key() == Qt.Key_D:
            self.move_right = False

    # =========================================================
    # SHOOTING
    # =========================================================

    def shoot(self):
        dx = self.mouse_x - self.player_x
        dy = self.mouse_y - self.player_y

        distance = (dx**2 + dy**2) ** 0.5

        if distance == 0:
            return

        # Normalize direction
        dx /= distance
        dy /= distance

        self.outgoing.put(
            {
                "type": "shoot",
                "x": self.player_x,
                "y": self.player_y,
                "dx": dx,
                "dy": dy,
            }
        )

    # =========================================================
    # CHAT INPUT
    # =========================================================

    def handle_chat_enter(self):
        if not self.typing_chat:
            self.typing_chat = True
            self.current_chat_input = ""
            self.update()
            return

        message = self.current_chat_input.strip()

        if message:
            self.send_chat(message)

        self.current_chat_input = ""
        self.typing_chat = False
        self.update()

    



if __name__ == "__main__":
    app = QApplication(sys.argv)

    game = Game()
    game.show()

    sys.exit(app.exec_())