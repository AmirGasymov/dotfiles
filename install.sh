#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="$HOME/.config"
APPS=(hypr waybar wofi)

if ! command -v pacman >/dev/null; then
  echo "Скрипт только для Arch Linux (нужен pacman)."
  exit 1
fi

echo "==> Основные пакеты"
sudo pacman -S --needed --noconfirm \
  hyprland hyprpaper wofi waybar \
  python-gobject gtk3 gtk-layer-shell \
  networkmanager bluez bluez-utils \
  ttf-jetbrains-mono-nerd pavucontrol curl

echo "==> Сервисы"
sudo systemctl enable --now bluetooth NetworkManager

for app in "${APPS[@]}"; do
  [ -d "$DIR/$app" ] || continue
  if [ -d "$CFG/$app" ]; then
    BACKUP="$CFG/$app.bak.$(date +%Y%m%d-%H%M%S)"
    echo "==> Бэкап $app в $BACKUP"
    mv "$CFG/$app" "$BACKUP"
  fi
  echo "==> Копирую $app"
  mkdir -p "$CFG/$app"
  cp -r "$DIR/$app/." "$CFG/$app/"
  grep -rlI "/home/amir" "$CFG/$app" 2>/dev/null | xargs -r sed -i "s#/home/amir#$HOME#g"
done

chmod +x "$CFG/waybar/popup.py"

if [ -d "$DIR/wallpapers" ]; then
  echo "==> Обои"
  mkdir -p "$HOME/Pictures"
  cp -r "$DIR/wallpapers/." "$HOME/Pictures/"
fi

if [ -f "$DIR/packages-official.txt" ]; then
  read -r -p "Установить полный список пакетов из packages-official.txt? [y/N] " a
  if [[ "$a" =~ ^[Yy]$ ]]; then
    sudo pacman -S --needed - < "$DIR/packages-official.txt" || true
  fi
fi

if [ -f "$DIR/packages-aur.txt" ] && command -v yay >/dev/null; then
  read -r -p "Установить AUR-пакеты через yay? [y/N] " a
  if [[ "$a" =~ ^[Yy]$ ]]; then
    yay -S --needed - < "$DIR/packages-aur.txt" || true
  fi
fi

echo "==> Готово. Перезайди в Hyprland или выполни: hyprctl reload; pkill waybar; waybar &"
