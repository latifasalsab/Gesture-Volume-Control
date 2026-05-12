# Tutorial: Gesture Volume Control 🎛️

> Tugas Besar — Pengolahan Citra  
> Sistem kendali volume menggunakan gesture tangan secara real-time

---

## Daftar Isi

1. [Cara Install](#1-cara-install)
2. [Cara Menjalankan](#2-cara-menjalankan)
3. [Panduan Gesture](#3-panduan-gesture)
4. [Penjelasan Kode](#4-penjelasan-kode)
5. [Konsep Pengolahan Citra](#5-konsep-pengolahan-citra)
6. [Troubleshooting](#6-troubleshooting)
7. [Pengembangan Lanjutan](#7-pengembangan-lanjutan)

---

## 1. Cara Install

### Prerequisites

- Python 3.8 – 3.11 (MediaPipe belum support Python 3.12+)
- Webcam (internal laptop / eksternal USB)
- OS Windows (untuk kontrol audio via `pycaw`)

### Install semua library

```bash
pip install opencv-python mediapipe numpy pycaw comtypes
```

Penjelasan tiap library:

| Library | Kegunaan |
|---|---|
| `opencv-python` | Baca kamera, gambar overlay di frame |
| `mediapipe` | Deteksi & tracking 21 landmark tangan (model buatan Google) |
| `numpy` | Operasi array gambar dan interpolasi nilai |
| `pycaw` | Kontrol volume audio sistem Windows |
| `comtypes` | Dependency dari pycaw untuk interface COM Windows |

### Struktur file

```
📁 project/
├── HandTrackingModule.py   ← modul deteksi tangan (kelas HandDetector)
├── gesture_volume.py       ← program utama (jalankan file ini)
└── TUTORIAL.md             ← file ini
```

---

## 2. Cara Menjalankan

```bash
python gesture_volume.py
```

Jika kamera tidak terbuka (error), coba ganti `CAM_ID = 1` di bagian
konfigurasi di `gesture_volume.py` (baris ~40).

Tekan **`Q`** untuk keluar dan melihat ringkasan statistik sesi di terminal.

---

## 3. Panduan Gesture

| Gesture | Cara Melakukan | Efek |
|---|---|---|
| **Pinch** | Dekatkan ujung jempol + telunjuk, lalu renggangkan | Atur volume (dekat = kecil, jauh = besar) |
| **Fist** | Kepalkan semua jari, tahan sebentar | Toggle mute / unmute |
| **Open Palm** | Buka kelima jari lebar, tahan sebentar | Reset volume ke 50% |
| **Thumbs Up** | Hanya jempol berdiri, tahan sebentar | Volume naik +10% |
| **Peace / V** | Telunjuk + jari tengah berdiri seperti huruf V | Volume turun -10% |

> **Tips:** Untuk gesture "tahan sebentar" (Fist, Palm, Thumbs Up, Peace),
> kamu perlu menahan gesture sekitar **0.5 detik** sampai progress bar
> di panel kanan penuh. Ini mencegah volume berubah secara tidak sengaja.

---

## 4. Penjelasan Kode

### HandTrackingModule.py

#### Kelas `HandDetector`

Wrapper di atas MediaPipe. Fungsi-fungsi utamanya:

---

**`findHands(img)`** — Deteksi tangan dan gambar skeleton

```python
imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # MediaPipe butuh RGB
self.results = self.hands.process(imgRGB)       # proses dengan AI model
```

MediaPipe menggunakan model deep learning yang sudah dilatih untuk
mendeteksi tangan. Kita tidak perlu melatih model sendiri — cukup
panggil `.process()` dan hasilnya langsung ada.

---

**`findPosition(img)`** — Ambil koordinat 21 landmark

```python
for lm_id, lm in enumerate(myHand.landmark):
    cx = int(lm.x * w)   # lm.x adalah nilai 0.0-1.0, kita kalikan lebar frame
    cy = int(lm.y * h)   # lm.y adalah nilai 0.0-1.0, kita kalikan tinggi frame
```

Koordinat dari MediaPipe dalam bentuk **normalized** (0.0–1.0).
Kita konversi ke piksel dengan mengalikan ukuran frame.

---

**`fingersUp()`** — Cek jari mana yang berdiri

```python
# Untuk jari telunjuk sampai kelingking:
# Jika ujung jari (tip) posisi Y-nya LEBIH KECIL dari sendi bawah (MCP),
# berarti jari berdiri (ingat: Y=0 di ATAS layar)
if self.lmList[tip][2] < self.lmList[mcp][2]:
    fingers.append(1)   # berdiri
```

Sistem koordinat layar: **Y bertambah ke bawah**.
Maka jari yang "berdiri" punya nilai Y lebih kecil (lebih dekat ke atas layar).

---

**`findDistance(p1, p2)`** — Jarak dua landmark

```python
length = math.hypot(x2 - x1, y2 - y1)
# Sama dengan: sqrt((x2-x1)^2 + (y2-y1)^2)
```

Rumus jarak Euclidean 2D. Ini yang dipakai untuk mengukur seberapa
jauh jempol dari telunjuk saat gesture pinch.

---

**`classifyGesture()`** — Klasifikasi gesture

```python
# Cek pinch: jarak jempol-telunjuk < 50 piksel
if dist_pinch < 50:
    return 'PINCH'

# Cek fist: semua jari melipat
if fingers == [0, 0, 0, 0, 0]:
    return 'FIST'
```

Klasifikasi berbasis **rule-based** (aturan logika manual), bukan machine
learning tambahan. Ini cukup untuk gesture yang tidak terlalu kompleks
dan lebih mudah dipahami dan di-debug.

---

### gesture_volume.py

#### Kelas `GestureState`

Menyimpan semua state aplikasi:
- `vol_pct` — volume saat ini dalam persen
- `is_muted` — status mute
- `gesture_hold` — counter frame untuk gesture "tahan"
- `vol_history` — riwayat volume untuk grafik mini
- `gesture_log` — log semua gesture untuk statistik sesi

---

#### Fungsi `handle_pinch()`

```python
# 1. Map jarak ke persen volume
raw_vol = np.interp(length, [40, 180], [0, 100])

# 2. EMA smoothing agar gerakan halus
state.smooth_vol = (alpha * raw_vol + (1 - alpha) * state.smooth_vol)

# 3. Bulatkan ke kelipatan SMOOTHNESS
state.vol_pct = SMOOTHNESS * round(state.smooth_vol / SMOOTHNESS)
```

**`np.interp`** adalah fungsi interpolasi linear:
- Jarak 40 piksel → volume 0%
- Jarak 180 piksel → volume 100%
- Nilai di antaranya dihitung proporsional

**EMA (Exponential Moving Average):**
```
vol_baru = alpha × input + (1-alpha) × vol_lama
```
Alpha kecil (0.1) = sangat halus tapi lambat respons.
Alpha besar (0.9) = cepat respons tapi bisa jitter.
Nilai 0.25 adalah keseimbangan yang baik.

---

#### Mekanisme Gesture Hold

Untuk mencegah gesture tidak sengaja trigger aksi:

```python
if gesture == state.prev_gesture:
    state.gesture_hold += 1   # gesture konsisten, tambah counter
else:
    state.gesture_hold = 0    # gesture berubah, reset counter

if state.gesture_hold >= HOLD_FRAMES:   # cukup konsisten
    handle_one_shot(state, gesture)     # jalankan aksi
    state.gesture_hold = 0
```

`HOLD_FRAMES = 12` artinya gesture harus konsisten selama 12 frame
(sekitar 0.4 detik di 30 FPS) sebelum aksi dijalankan.

---

## 5. Konsep Pengolahan Citra

### Alur pemrosesan frame

```
Webcam → Frame BGR → Konversi ke RGB → MediaPipe → Landmark
   ↓
Landmark (21 titik x,y) → Hitung jarak & jari → Klasifikasi gesture
   ↓
Gesture → Aksi volume → Update UI → Tampil ke layar
```

### Ruang warna BGR vs RGB

OpenCV membaca gambar dalam format **BGR** (Blue-Green-Red),
berbeda dari format standar **RGB** (Red-Green-Blue).
MediaPipe membutuhkan RGB, sehingga konversi diperlukan:

```python
imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
```

### Koordinat piksel

Frame video adalah array NumPy 3 dimensi: `(height, width, channel)`.
- `img[y][x]` = piksel di baris y, kolom x
- `img[y][x][0]` = nilai kanal biru (B)
- `img[y][x][1]` = nilai kanal hijau (G)
- `img[y][x][2]` = nilai kanal merah (R)

### Landmark MediaPipe

MediaPipe mendeteksi **21 titik** per tangan:

```
Nomor landmark penting:
  0  = pergelangan tangan (wrist)
  4  = ujung jempol (thumb tip)
  8  = ujung telunjuk (index tip)
  12 = ujung jari tengah (middle tip)
  16 = ujung jari manis (ring tip)
  20 = ujung kelingking (pinky tip)

  1-3   = ruas-ruas jempol
  5-7   = ruas-ruas telunjuk
  9-11  = ruas-ruas jari tengah
  13-15 = ruas-ruas jari manis
  17-19 = ruas-ruas kelingking
```

---

## 6. Troubleshooting

### Kamera tidak terbuka
```
[ERROR] Kamera 0 tidak bisa dibuka!
```
→ Ganti `CAM_ID = 1` (atau 2) di baris konfigurasi `gesture_volume.py`

### Audio tidak terkontrol
```
[WARN] Audio backend tidak tersedia
```
→ Pastikan `pycaw` dan `comtypes` terinstall.
→ Coba jalankan sebagai Administrator.
→ Pastikan OS Windows (pycaw tidak support Linux/Mac).

### Gesture tidak terdeteksi dengan baik
- Pastikan pencahayaan cukup
- Jaga tangan dalam bounding box kamera
- Jarak tangan ke kamera sekitar 30–60 cm
- Coba kurangi `detectionCon` dari 0.75 ke 0.6

### FPS terlalu rendah (< 15 FPS)
- Kurangi resolusi: ganti `CAM_W = 640`, `CAM_H = 480`
- Tutup aplikasi lain yang berat

---

## 7. Pengembangan Lanjutan

Beberapa ide untuk dikembangkan lebih lanjut:

### Swipe gesture untuk step volume
Bisa diimplementasikan dengan tracking posisi tangan antar frame:
```python
# Simpan posisi X tangan frame sebelumnya
# Jika posisi X bergerak > threshold dalam beberapa frame → swipe
delta_x = current_x - prev_x
if delta_x > 50:   # swipe kanan
    ...
```

### Multi-hand support
Ganti `maxHands=1` ke `maxHands=2` dan loop semua tangan yang terdeteksi.

### Ekspor statistik ke CSV
```python
import csv
with open('sesi_log.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerows(state.gesture_log)
```

### Kalibrasi jarak pinch
Tampilkan UI kalibrasi di awal sesi supaya rentang pinch menyesuaikan
ukuran tangan pengguna.
