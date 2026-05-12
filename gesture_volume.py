"""
gesture_volume.py
=================
Program utama: kendalikan volume sistem dengan gesture tangan.

Gesture yang didukung:
  PINCH      → dekatkan/renggangkan jempol+telunjuk untuk atur volume
  FIST       → mute / unmute toggle
  OPEN_PALM  → reset volume ke 50%
  THUMBS_UP  → volume naik +10%
  PEACE (V)  → volume turun -10%

Layout window:
  [ Kamera 960px ] [ Sidebar Dashboard 320px ]

Tekan 'q' untuk keluar.

Dependencies:
  pip install opencv-python mediapipe numpy pycaw comtypes
"""

import cv2
import time
import numpy as np
from collections import deque, Counter

import HandTrackingModule as htm

# ── Audio backend ────────────────────────────────────────────────
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices   = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume    = cast(interface, POINTER(IAudioEndpointVolume))
    AUDIO_OK  = True
    print("[OK] Audio backend: pycaw")
except Exception as e:
    AUDIO_OK = False
    print(f"[WARN] Audio tidak tersedia: {e}")


# ══════════════════════════════════════════════════════════════════
# KONFIGURASI
# ══════════════════════════════════════════════════════════════════

CAM_ID      = 0
CAM_W       = 960        # lebar area kamera
CAM_H       = 720
SIDE_W      = 320        # lebar sidebar dashboard
TOTAL_W     = CAM_W + SIDE_W
SMOOTHNESS  = 5
HOLD_FRAMES = 12

# Warna UI (BGR)
C_WHITE  = (255, 255, 255)
C_BLACK  = (0,   0,   0  )
C_GREEN  = (80,  220, 100)
C_RED    = (70,  70,  230)
C_BLUE   = (230, 150, 50 )
C_YELLOW = (30,  220, 220)
C_PURPLE = (210, 90,  170)
C_GRAY   = (160, 160, 160)
C_ORANGE = (40,  150, 255)
C_DARK   = (25,  25,  25 )
C_PANEL  = (35,  35,  35 )

GESTURE_COLORS = {
    'PINCH':     C_BLUE,
    'FIST':      C_RED,
    'OPEN_PALM': C_GREEN,
    'THUMBS_UP': C_YELLOW,
    'PEACE':     C_PURPLE,
    'POINTING':  C_ORANGE,
    'UNKNOWN':   C_GRAY,
}

GESTURE_LABEL = {
    'PINCH':     'PINCH',
    'FIST':      'FIST',
    'THUMBS_UP': 'FOUR FINGERS',
    'PEACE':     'PEACE',
    'POINTING':  'POINTING',
    'UNKNOWN':   'UNKNOWN',
}

GESTURE_DESC = {
    'PINCH':
        ['Dekatkan jempol + telunjuk',
         'Dekat = vol kecil, jauh = besar',
         'Renggangkan perlahan'],
    'FIST':
        ['Kepalkan semua jari',
         'Tahan sebentar',
         'Toggle mute / unmute'],
    'THUMBS_UP':
        ['Angkat 4 jari (tanpa jempol)',
         'Tahan sebentar',
         'Volume naik +10%'],
    'PEACE':
        ['Telunjuk + jari tengah berdiri',
         'Tahan sebentar',
         'Volume turun -10%'],
    'UNKNOWN':
        ['Tunjukkan tangan ke kamera',
         'dengan posisi jelas',
         'dan pencahayaan cukup'],
    'POINTING':
        ['Gesture tidak terdefinisi',
         'Coba gesture lain', ''],
}


# ══════════════════════════════════════════════════════════════════
# STATE
# ══════════════════════════════════════════════════════════════════

class GestureState:
    def __init__(self):
        self.vol_pct          = 50.0
        self.is_muted         = False
        self.vol_before_mute  = 50.0
        self.smooth_vol       = 50.0
        self.ema_alpha        = 0.2

        self.current_gesture  = 'UNKNOWN'
        self.prev_gesture     = 'UNKNOWN'
        self.gesture_hold     = 0
        self.last_action_time = 0.0
        self.action_cooldown  = 1.0

        self.pinch_length     = 0.0
        self.pinch_active     = False

        self.session_start    = time.time()
        self.gesture_log      = []
        self.gesture_counts   = Counter()
        self.vol_history      = deque(maxlen=150)
        self.action_history   = deque(maxlen=8)

        self.pTime = time.time()
        self.fps   = 0

    def log_gesture(self, gesture):
        self.gesture_log.append((time.time(), gesture))
        self.gesture_counts[gesture] += 1

    def log_action(self, msg):
        self.action_history.append((time.time(), msg))

    def session_duration(self):
        return time.time() - self.session_start


# ══════════════════════════════════════════════════════════════════
# AUDIO
# ══════════════════════════════════════════════════════════════════

def set_system_volume(pct):
    if not AUDIO_OK:
        return
    volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, pct / 100.0)), None)

def get_system_volume():
    if not AUDIO_OK:
        return 50.0
    return volume.GetMasterVolumeLevelScalar() * 100.0


# ══════════════════════════════════════════════════════════════════
# GESTURE HANDLERS
# ══════════════════════════════════════════════════════════════════

def handle_pinch(state, length):
    raw_vol = np.interp(length, [20, 180], [0, 100])
    state.smooth_vol = state.ema_alpha * raw_vol + (1 - state.ema_alpha) * state.smooth_vol
    state.vol_pct    = SMOOTHNESS * round(state.smooth_vol / SMOOTHNESS)
    state.vol_pct    = max(0, min(100, state.vol_pct))
    state.pinch_length = length
    state.pinch_active = True
    if not state.is_muted:
        set_system_volume(state.vol_pct)

def handle_one_shot(state, gesture):
    now = time.time()
    if now - state.last_action_time < state.action_cooldown:
        return

    if gesture == 'FIST':
        if state.is_muted:
            state.vol_pct  = state.vol_before_mute
            state.is_muted = False
            set_system_volume(state.vol_pct)
            state.log_action(f'Unmute -> {int(state.vol_pct)}%')
        else:
            state.vol_before_mute = state.vol_pct
            state.is_muted = True
            set_system_volume(0)
            state.log_action('Mute')

    elif gesture == 'THUMBS_UP':
        state.vol_pct  = min(100, state.vol_pct + 10)
        state.is_muted = False
        set_system_volume(state.vol_pct)
        state.log_action(f'Vol +10 -> {int(state.vol_pct)}%')

    elif gesture == 'PEACE':
        state.vol_pct  = max(0, state.vol_pct - 10)
        state.is_muted = False
        set_system_volume(state.vol_pct)
        state.log_action(f'Vol -10 -> {int(state.vol_pct)}%')

    state.last_action_time = now
    state.log_gesture(gesture)


# ══════════════════════════════════════════════════════════════════
# UI — AREA KAMERA
# ══════════════════════════════════════════════════════════════════

def draw_volume_bar(cam, state):
    bx, bt, bb, bw = 30, 130, 480, 28
    bh     = bb - bt
    fill_h = int(bh * state.vol_pct / 100)
    color  = C_RED if state.is_muted else C_GREEN

    cv2.rectangle(cam, (bx, bt), (bx + bw, bb), C_GRAY, 1)
    if fill_h > 0:
        cv2.rectangle(cam, (bx, bb - fill_h), (bx + bw, bb), color, cv2.FILLED)

    label = 'MUTE' if state.is_muted else f'{int(state.vol_pct)}%'
    cv2.putText(cam, 'VOL', (bx, bt - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, C_GRAY, 1)
    cv2.putText(cam, label, (bx - 2, bb + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def draw_pinch_feedback(cam, state, lineInfo):
    """
    Feedback visual pinch yang lengkap:
    - Garis & titik antara jempol dan telunjuk
    - Lingkaran tengah ukurannya sesuai volume
    - Angka volume besar di tengah atas
    - Bar horizontal penanda posisi volume
    """
    x1, y1, x2, y2, cx, cy = lineInfo

    # Warna dinamis: biru (kecil) -> hijau -> merah (besar)
    ratio = state.vol_pct / 100.0
    r = int(70  + 160 * ratio)
    g = int(220 - 140 * ratio)
    b = 80
    color = (b, g, r)

    # Garis dan titik ujung
    cv2.line(cam, (x1, y1), (x2, y2), color, 3)
    cv2.circle(cam, (x1, y1), 14, color, cv2.FILLED)
    cv2.circle(cam, (x2, y2), 14, color, cv2.FILLED)

    # Label jempol & telunjuk
    cv2.putText(cam, 'Jempol', (x1 - 35, y1 - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)
    cv2.putText(cam, 'Telunjuk', (x2 - 40, y2 - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)

    # Lingkaran tengah — makin besar makin tinggi volume
    radius = int(np.interp(state.vol_pct, [0, 100], [10, 42]))
    cv2.circle(cam, (cx, cy), radius, color, cv2.FILLED)
    cv2.circle(cam, (cx, cy), radius + 5, color, 2)

    # Label jarak di dalam lingkaran
    dist_text = f'{int(state.pinch_length)}px'
    cv2.putText(cam, dist_text, (cx - 20, cy + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_BLACK, 1)

    # ── Angka volume besar di tengah atas ──────────────────────
    vol_text = 'MUTE' if state.is_muted else f'{int(state.vol_pct)}%'
    fs = 2.2
    tw = cv2.getTextSize(vol_text, cv2.FONT_HERSHEY_SIMPLEX, fs, 4)[0][0]
    tx = (CAM_W - tw) // 2
    ty = 88

    # Shadow
    cv2.putText(cam, vol_text, (tx + 3, ty + 3),
                cv2.FONT_HERSHEY_SIMPLEX, fs, C_BLACK, 6)
    # Teks
    cv2.putText(cam, vol_text, (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX, fs, color, 4)

    # ── Bar horizontal volume ───────────────────────────────────
    bx0 = CAM_W // 2 - 160
    bx1 = CAM_W // 2 + 160
    by  = 102
    bfill = int(bx0 + (bx1 - bx0) * ratio)

    cv2.rectangle(cam, (bx0, by), (bx1, by + 10), (55, 55, 55), cv2.FILLED)
    if int(state.vol_pct) > 0:
        cv2.rectangle(cam, (bx0, by), (bfill, by + 10), color, cv2.FILLED)
    cv2.rectangle(cam, (bx0, by), (bx1, by + 10), C_GRAY, 1)

    # Label 0% dan 100%
    cv2.putText(cam, '0%', (bx0 - 2, by + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_GRAY, 1)
    cv2.putText(cam, '100%', (bx1 - 32, by + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_GRAY, 1)

    # Petunjuk cara pinch
    cv2.putText(cam, 'Dekat = kecil  |  Jauh = besar',
                (CAM_W // 2 - 130, by + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_GRAY, 1)


def draw_gesture_info(cam, state):
    """Panel gesture aktif + instruksi cara melakukan + hold bar."""
    gesture = state.current_gesture
    color   = GESTURE_COLORS.get(gesture, C_GRAY)
    label   = GESTURE_LABEL.get(gesture, gesture)
    descs   = GESTURE_DESC.get(gesture, [])

    px, py = CAM_W - 300, 15
    ph     = 165

    overlay = cam.copy()
    cv2.rectangle(overlay, (px - 8, py), (CAM_W - 8, py + ph),
                  C_DARK, cv2.FILLED)
    cv2.addWeighted(overlay, 0.72, cam, 0.28, 0, cam)
    cv2.rectangle(cam, (px - 8, py), (CAM_W - 8, py + ph), color, 2)

    cv2.putText(cam, label, (px, py + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    for i, line in enumerate(descs):
        cv2.putText(cam, line, (px, py + 54 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_GRAY, 1)

    # Hold progress bar
    if gesture not in ('PINCH', 'UNKNOWN', 'POINTING'):
        hold_pct = min(state.gesture_hold / HOLD_FRAMES, 1.0)
        bw_total = CAM_W - 16 - px
        bw_fill  = int(bw_total * hold_pct)
        by_bar   = py + ph - 30

        cv2.putText(cam, 'Tahan:', (px, by_bar - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_GRAY, 1)
        cv2.rectangle(cam, (px + 55, by_bar - 14),
                      (px + 55 + bw_total, by_bar), (60, 60, 60), cv2.FILLED)
        if bw_fill > 0:
            cv2.rectangle(cam, (px + 55, by_bar - 14),
                          (px + 55 + bw_fill, by_bar), color, cv2.FILLED)

    # Cooldown
    cd = max(0.0, state.action_cooldown - (time.time() - state.last_action_time))
    if cd > 0:
        cv2.putText(cam, f'Cooldown {cd:.1f}s', (px, py + ph - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_RED, 1)


def draw_fps_dur(cam, state):
    cTime      = time.time()
    state.fps  = 1 / max(cTime - state.pTime, 1e-9)
    state.pTime = cTime
    dur = int(state.session_duration())
    cv2.putText(cam, f'FPS {int(state.fps)}', (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_GRAY, 1)
    cv2.putText(cam, f'{dur//60:02d}:{dur%60:02d}', (10, 44),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_GRAY, 1)


# ══════════════════════════════════════════════════════════════════
# UI — SIDEBAR DASHBOARD
# ══════════════════════════════════════════════════════════════════

def draw_sidebar(state, height=720):
    sb = np.zeros((height, SIDE_W, 3), dtype=np.uint8)
    sb[:] = C_DARK

    y = 0

    # ── Header ─────────────────────────────────────────────────
    cv2.rectangle(sb, (0, 0), (SIDE_W, 40), C_PANEL, cv2.FILLED)
    cv2.putText(sb, 'DASHBOARD', (10, 27),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, C_YELLOW, 2)
    dur = int(state.session_duration())
    cv2.putText(sb, f'{dur//60:02d}:{dur%60:02d}', (SIDE_W - 58, 27),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_GRAY, 1)
    y = 48

    # ── Volume meter ────────────────────────────────────────────
    cv2.putText(sb, 'VOLUME SEKARANG', (10, y + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_GRAY, 1)
    y += 18

    vol_color = C_RED if state.is_muted else C_GREEN
    vol_text  = 'MUTE' if state.is_muted else f'{int(state.vol_pct)}%'
    cv2.putText(sb, vol_text, (10, y + 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.7, vol_color, 3)

    bx0, bx1 = 10, SIDE_W - 10
    by = y + 60
    bfill = int(bx0 + (bx1 - bx0) * state.vol_pct / 100)
    cv2.rectangle(sb, (bx0, by), (bx1, by + 14), (55, 55, 55), cv2.FILLED)
    if not state.is_muted and int(state.vol_pct) > 0:
        cv2.rectangle(sb, (bx0, by), (bfill, by + 14), vol_color, cv2.FILLED)
    cv2.rectangle(sb, (bx0, by), (bx1, by + 14), C_GRAY, 1)
    y = by + 24

    # ── Riwayat volume ──────────────────────────────────────────
    cv2.line(sb, (0, y), (SIDE_W, y), (50, 50, 50), 1)
    y += 8
    cv2.putText(sb, 'RIWAYAT VOLUME', (10, y + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_GRAY, 1)
    y += 18

    gh  = 68
    gx0, gx1 = 10, SIDE_W - 10
    gw = gx1 - gx0

    cv2.rectangle(sb, (gx0, y), (gx1, y + gh), (45, 45, 45), cv2.FILLED)
    cv2.rectangle(sb, (gx0, y), (gx1, y + gh), (70, 70, 70), 1)

    # Grid 50%
    gy50 = y + gh - int(gh * 0.5)
    cv2.line(sb, (gx0, gy50), (gx1, gy50), (65, 65, 65), 1)
    cv2.putText(sb, '50', (gx1 + 2, gy50 + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (80, 80, 80), 1)

    if len(state.vol_history) >= 2:
        vlist = list(state.vol_history)
        pts = [(gx0 + int(i * gw / len(vlist)),
                y + gh - int(v * gh / 100))
               for i, v in enumerate(vlist)]
        for i in range(1, len(pts)):
            cv2.line(sb, pts[i - 1], pts[i], C_GREEN, 1)

    y += gh + 10

    # ── Statistik gesture ───────────────────────────────────────
    cv2.line(sb, (0, y), (SIDE_W, y), (50, 50, 50), 1)
    y += 8
    cv2.putText(sb, 'STATISTIK GESTURE', (10, y + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_GRAY, 1)
    y += 20

    total = sum(state.gesture_counts.values()) or 1
    top5  = state.gesture_counts.most_common(5)
    bar_max_w = SIDE_W - 130

    if top5:
        for gname, count in top5:
            gcol    = GESTURE_COLORS.get(gname, C_GRAY)
            short   = gname[:11]
            bar_len = int(bar_max_w * count / total)
            cv2.putText(sb, short, (10, y + 11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, gcol, 1)
            if bar_len > 0:
                cv2.rectangle(sb, (105, y), (105 + bar_len, y + 12),
                              gcol, cv2.FILLED)
            cv2.putText(sb, str(count), (108 + bar_len, y + 11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, C_GRAY, 1)
            y += 18
    else:
        cv2.putText(sb, 'Belum ada gesture', (10, y + 11),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_GRAY, 1)
        y += 18

    y += 4

    # ── Log aksi ────────────────────────────────────────────────
    cv2.line(sb, (0, y), (SIDE_W, y), (50, 50, 50), 1)
    y += 8
    cv2.putText(sb, 'AKSI TERAKHIR', (10, y + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_GRAY, 1)
    y += 20

    now_t   = time.time()
    recent  = list(state.action_history)[-5:]
    if recent:
        for ts, msg in reversed(recent):
            age  = now_t - ts
            fade = max(80, 220 - int(age * 25))
            col  = (fade, fade, fade)
            cv2.putText(sb, f'{age:4.0f}s  {msg}', (10, y + 11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, col, 1)
            y += 16
    else:
        cv2.putText(sb, 'Belum ada aksi', (10, y + 11),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_GRAY, 1)
        y += 16

    y += 6

    # ── Panduan gesture ─────────────────────────────────────────
    if height - y > 70:
        cv2.line(sb, (0, y), (SIDE_W, y), (50, 50, 50), 1)
        y += 8
        cv2.putText(sb, 'PANDUAN', (10, y + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, C_GRAY, 1)
        y += 20
        guides = [
            ('PINCH',     'Atur volume'),
            ('FIST',      'Mute toggle'),
            ('THUMBS_UP', 'Vol +10% (4 jari)'),
            ('PEACE',     'Vol -10%'),
        ]
        for gkey, desc in guides:
            if y + 16 > height - 10:
                break
            col = GESTURE_COLORS.get(gkey, C_GRAY)
            short = GESTURE_LABEL.get(gkey, gkey)
            cv2.putText(sb, f'{short}: {desc}', (10, y + 11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, col, 1)
            y += 16

    # Garis pemisah kiri
    cv2.line(sb, (0, 0), (0, height), (70, 70, 70), 2)
    return sb


# ══════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════

def main():
    print('\nGesture Volume Control')
    print('=' * 40)

    cap = cv2.VideoCapture(CAM_ID)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)

    if not cap.isOpened():
        print(f'[ERROR] Kamera {CAM_ID} tidak bisa dibuka. Coba CAM_ID = 1')
        return

    detector = htm.HandDetector(detectionCon=0.75, maxHands=1)
    state    = GestureState()
    state.vol_pct    = get_system_volume()
    state.smooth_vol = state.vol_pct

    print(f'[OK] Kamera aktif ({CAM_W}x{CAM_H})')
    print(f'[OK] Volume awal  {state.vol_pct:.0f}%')
    print('Tunjukkan tangan ke kamera!\n')

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        frame = cv2.flip(frame, 1)

        # ── Deteksi tangan ────────────────────────────────────
        frame        = detector.findHands(frame, draw=True)
        lmList, bbox = detector.findPosition(frame, draw=False)
        state.pinch_active = False

        if len(lmList) > 0:
            gesture               = detector.classifyGesture()
            state.current_gesture = gesture

            if gesture == 'PINCH':
                length, frame, lineInfo = detector.findDistance(4, 8, frame)
                handle_pinch(state, length)
                draw_pinch_feedback(frame, state, lineInfo)
                state.gesture_hold = 0

            elif gesture in ('FIST', 'THUMBS_UP', 'PEACE'):
                if gesture == state.prev_gesture:
                    state.gesture_hold += 1
                else:
                    state.gesture_hold = 0
                if state.gesture_hold >= HOLD_FRAMES:
                    handle_one_shot(state, gesture)
                    state.gesture_hold = 0
            else:
                state.gesture_hold = 0

            state.prev_gesture = gesture
        else:
            state.current_gesture = 'UNKNOWN'
            state.gesture_hold    = 0
            state.prev_gesture    = 'UNKNOWN'

        state.vol_history.append(state.vol_pct)

        # ── Gambar UI kamera ──────────────────────────────────
        draw_fps_dur(frame, state)
        draw_volume_bar(frame, state)
        if state.current_gesture != 'PINCH':
            draw_gesture_info(frame, state)

        # ── Sidebar & gabung ──────────────────────────────────
        actual_h = frame.shape[0]   # tinggi frame aktual dari kamera
        sidebar  = draw_sidebar(state, actual_h)
        combined = np.hstack([frame, sidebar])

        cv2.imshow('Gesture Volume Control', combined)

        if cv2.waitKey(1) & 0xFF in (ord('q'), ord('Q')):
            break

    cap.release()
    cv2.destroyAllWindows()

    dur = int(state.session_duration())
    print(f'\n{"="*45}')
    print(f'  RINGKASAN SESI  ({dur//60:02d}:{dur%60:02d})')
    print(f'{"="*45}')
    if state.gesture_counts:
        for g, c in state.gesture_counts.most_common():
            bar = 'X' * (c * 20 // max(state.gesture_counts.values()))
            print(f'  {g:<12} {bar} {c}x')
    print(f'{"="*45}\n')


if __name__ == '__main__':
    main()