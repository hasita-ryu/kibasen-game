import sys
import time
from pathlib import Path

import pygame

WIDTH = 960
HEIGHT = 540
FPS = 60
MAX_HP = 100
TIME_DAMAGE = 1
TIME_DAMAGE_INTERVAL = 3
VIBRATION_DAMAGE = 2
LIGHT_DAMAGE = 4
SPACE_DAMAGE = 5

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"

ASSETS = {
    "background": ASSET_DIR / "background.png",
    "sleep": ASSET_DIR / "vampire_sleep.png",
    "wake_1": ASSET_DIR / "vampire_wake_1.png",
    "wake_2": ASSET_DIR / "vampire_wake_2.png",
    "damage": ASSET_DIR / "vampire_damage.png",
}

BG = (10, 8, 20)
HP_BACK = (24, 18, 35)
HP_BORDER = (238, 224, 255)
HP_FILL = (202, 35, 64)
HP_FILL_DARK = (97, 15, 32)
TEXT = (255, 240, 246)
JP_FONT_CANDIDATES = [
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc"),
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
]


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def make_font(size, bold=False):
    for path in JP_FONT_CANDIDATES:
        if path.exists():
            return pygame.font.Font(str(path), size)

    return pygame.font.SysFont("Arial", size, bold=bold)


def load_image(path, size=None, remove_edge_background=False):
    image = pygame.image.load(path).convert_alpha()

    if size is not None:
        image = pygame.transform.scale(image, size)

    return image


def transparent_edge_background(image):
    width, height = image.get_size()
    pixels = pygame.PixelArray(image)
    queue = []
    seen = set()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.pop()
        if (x, y) in seen or x < 0 or y < 0 or x >= width or y >= height:
            continue
        seen.add((x, y))

        color = image.unmap_rgb(pixels[x, y])
        if is_removable_background(color):
            pixels[x, y] = (255, 255, 255, 0)
            queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    del pixels
    image = remove_light_fringe(image, passes=14)
    return image


def is_removable_background(color, aggressive=False):
    if color.a < 8:
        return True

    brightest = max(color.r, color.g, color.b)
    darkest = min(color.r, color.g, color.b)
    if aggressive:
        return (darkest > 85 and brightest - darkest < 135) or (
            color.r > 165 and color.g > 165 and color.b > 165
        )

    is_light_neutral = darkest > 150 and brightest - darkest < 70
    is_checker_white = color.r > 215 and color.g > 215 and color.b > 215
    return is_light_neutral or is_checker_white


def remove_light_fringe(image, passes=2):
    width, height = image.get_size()
    source = image.copy()
    source_pixels = pygame.PixelArray(source)
    target_pixels = pygame.PixelArray(image)

    for _ in range(passes):
        to_clear = []
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                color = source.unmap_rgb(source_pixels[x, y])
                if color.a < 8:
                    continue

                neighbor_transparent = False
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if source.unmap_rgb(source_pixels[nx, ny]).a < 8:
                        neighbor_transparent = True
                        break

                if neighbor_transparent and is_removable_background(color, aggressive=True):
                    to_clear.append((x, y))

        for x, y in to_clear:
            target_pixels[x, y] = (255, 255, 255, 0)

        del source_pixels
        source = image.copy()
        source_pixels = pygame.PixelArray(source)

    for _ in range(4):
        to_clear = []
        for y in range(2, height - 2):
            for x in range(2, width - 2):
                color = source.unmap_rgb(source_pixels[x, y])
                if color.a < 8:
                    continue

                close_to_alpha = False
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        if source.unmap_rgb(source_pixels[x + dx, y + dy]).a < 8:
                            close_to_alpha = True
                            break
                    if close_to_alpha:
                        break

                brightest = max(color.r, color.g, color.b)
                darkest = min(color.r, color.g, color.b)
                pale_or_gray = (darkest > 75 and brightest - darkest < 150) or (
                    color.r > 150 and color.g > 150 and color.b > 150
                )
                if close_to_alpha and pale_or_gray:
                    to_clear.append((x, y))

        for x, y in to_clear:
            target_pixels[x, y] = (255, 255, 255, 0)

        del source_pixels
        source = image.copy()
        source_pixels = pygame.PixelArray(source)

    del source_pixels
    del target_pixels
    return image


class VampireHpGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("眠った吸血鬼を運べ")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = make_font(22, bold=True)
        self.help_font = make_font(15, bold=True)

        self.hp = MAX_HP
        self.last_tick = time.time()
        self.hit_started = 0
        self.frame = 0
        self.paused = False

        self.assets = self.load_assets()
        self.missing_assets = [key for key, path in ASSETS.items() if not path.exists()]

    def load_assets(self):
        assets = {}
        if ASSETS["background"].exists():
            assets["background"] = load_image(ASSETS["background"], (WIDTH, HEIGHT))

        for key in ("sleep", "wake_1", "wake_2", "damage"):
            if ASSETS[key].exists():
                assets[key] = load_image(ASSETS[key], remove_edge_background=True)

        return assets

    def run(self):
        while True:
            self.frame += 1
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    self.paused = True
                    self.hit_started = 0
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.damage(VIBRATION_DAMAGE)
                if event.key == pygame.K_SPACE:
                    self.damage(LIGHT_DAMAGE)
                if event.key == pygame.K_r:
                    self.hp = MAX_HP
                    self.hit_started = 0
                    self.paused = False
                    self.last_tick = time.time()

    def update(self):
        if self.paused:
            self.last_tick = time.time()
            return

        now = time.time()
        if self.hp > 0 and now - self.last_tick >= TIME_DAMAGE_INTERVAL:
            elapsed = int((now - self.last_tick) // TIME_DAMAGE_INTERVAL)
            self.hp = clamp(self.hp - elapsed * TIME_DAMAGE, 0, MAX_HP)
            self.last_tick += elapsed * TIME_DAMAGE_INTERVAL

    def damage(self, amount):
        if self.paused or self.hp <= 0:
            return
        self.hp = clamp(self.hp - amount, 0, MAX_HP)
        self.hit_started = time.time()

    def current_vampire_key(self):
        if self.hit_started == 0:
            return "sleep"

        elapsed = time.time() - self.hit_started
        wake_1 = "wake_1"
        wake_2 = "wake_2"
        damage = "damage"

        if elapsed < 0.16:
            return wake_1
        if elapsed < 0.34:
            return wake_2
        if elapsed < 0.74:
            return damage
        if elapsed < 0.92:
            return wake_2
        if elapsed < 1.08:
            return wake_1

        self.hit_started = 0
        return "sleep"

    def draw(self):
        if self.missing_assets:
            self.draw_missing_assets()
            pygame.display.flip()
            return

        self.draw_background()
        self.draw_vampire()
        self.draw_hp_bar()
        self.draw_help_overlay()
        pygame.display.flip()

    def draw_background(self):
        self.screen.blit(self.assets["background"], (0, 0))

    def draw_vampire(self):
        key = self.current_vampire_key()
        image = self.assets.get(key) or self.assets.get("sleep")

        target_width = 650
        scale = target_width / image.get_width()
        target_size = (target_width, int(image.get_height() * scale))
        sprite = pygame.transform.scale(image, target_size)
        rect = sprite.get_rect(center=(WIDTH // 2, 340))
        self.screen.blit(sprite, rect)

    def draw_hp_bar(self):
        x, y, w, h = 76, 34, 808, 34
        pygame.draw.rect(self.screen, HP_BACK, (x, y, w, h), border_radius=3)
        pygame.draw.rect(self.screen, HP_BORDER, (x - 4, y - 4, w + 8, h + 8), 4, border_radius=5)

        fill_w = int(w * self.hp / MAX_HP)
        if fill_w > 0:
            pygame.draw.rect(self.screen, HP_FILL_DARK, (x, y, fill_w, h), border_radius=3)
            pygame.draw.rect(self.screen, HP_FILL, (x, y, fill_w, h - 10), border_radius=3)

        label = self.font.render(f"HP {self.hp}", False, TEXT)
        self.screen.blit(label, (x + 12, y + 5))

        if self.paused:
            paused_label = self.help_font.render("STOP", False, TEXT)
            self.screen.blit(paused_label, (x + w - 64, y + 9))

    def draw_help_overlay(self):
        lines = ["Enter: MESH 振動", "Space: MESH 明るさ", "R: リセット", "Q: 停止"]
        line_height = 20
        padding_x = 14
        padding_y = 10
        width = 190
        height = padding_y * 2 + line_height * len(lines)
        x = WIDTH - width - 18
        y = HEIGHT - height - 18

        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (8, 6, 14, 145), overlay.get_rect(), border_radius=8)

        for index, line in enumerate(lines):
            text = self.help_font.render(line, False, (245, 235, 248))
            text.set_alpha(185)
            overlay.blit(text, (padding_x, padding_y + index * line_height))

        self.screen.blit(overlay, (x, y))

    def draw_missing_assets(self):
        self.screen.fill((12, 10, 18))
        title = self.font.render("画像ファイルが assets フォルダにありません", False, TEXT)
        self.screen.blit(title, (80, 70))

        small_font = pygame.font.SysFont("Arial", 18, bold=True)
        y = 130
        for key in self.missing_assets:
            line = small_font.render(str(ASSETS[key]), False, (255, 190, 200))
            self.screen.blit(line, (80, y))
            y += 34

        note = small_font.render("上の名前で画像を保存すると、この画面に反映されます。Qで終了。", False, (220, 210, 230))
        self.screen.blit(note, (80, y + 24))


if __name__ == "__main__":
    VampireHpGame().run()
