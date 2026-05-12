# 🎛️ Gesture Volume Control

> Tugas Besar — Pengolahan Citra  
> Sistem kendali volume audio menggunakan gesture tangan secara real-time berbasis computer vision

![Python](https://img.shields.io/badge/Python-3.8--3.11-blue)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-green)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10+-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## 📋 Deskripsi

Program ini memanfaatkan kamera webcam untuk mendeteksi gesture tangan secara real-time dan mengendalikan volume audio sistem tanpa menyentuh perangkat apapun. Sistem menggunakan **MediaPipe** untuk mendeteksi 21 landmark tangan, lalu mengklasifikasikan gesture menggunakan logika berbasis jarak dan posisi jari.

---

## ✋ Gesture yang Didukung

| Gesture | Cara Melakukan | Fungsi |
|---|---|---|
| 👌 **PINCH** | Dekat/renggangkan ujung jempol & telunjuk | Atur volume (slider kontinu) |
| ✊ **FIST** | Kepalkan semua jari, tahan sebentar | Toggle mute / unmute |
| 4️⃣ **FOUR FINGERS** | Angkat 4 jari (tanpa jempol), tahan sebentar | Volume naik +10% |
| ✌️ **PEACE** | Angkat telunjuk + jari tengah, tahan sebentar | Volume turun -10% |

> **Catatan:** Gesture "tahan sebentar" membutuhkan konsistensi ~0.5 detik sebelum aksi dijalankan untuk mencegah trigger tidak sengaja.

---

## 🖥️ Tampilan Aplikasi

```
┌─────────────────────────────┬──────────────────┐
│                             │   DASHBOARD      │
│      Area Kamera            │   Volume: 70%    │
│      (960 x 540)            │   ────────────   │
│                             │   Riwayat Vol    │
│  [Skeleton tangan]          │   ~~~~∿~~~~      │
│  [Bar volume kiri]          │   ────────────   │
│  [Panel gesture kanan]      │   Statistik      │
│  [FPS & durasi sesi]        │   PINCH  ████ 5x │
│                             │   FIST   ██   2x │
│                             │   ────────────   │
│                             │   Aksi Terakhir  │
│                             │   3s  Vol +10    │
└─────────────────────────────┴──────────────────┘
```

---

## 🛠️ Teknologi yang Digunakan

| Library | Versi | Kegunaan |
|---|---|---|
| `opencv-python` | ≥ 4.8 | Baca kamera, gambar overlay UI |
| `mediapipe` | 0.10.13 | Deteksi 21 landmark tangan |
| `numpy` | < 2.0 | Operasi array gambar & interpolasi |
| `pycaw` | 20230407 | Kontrol volume audio Windows |
| `comtypes` | latest | Dependency COM untuk pycaw |

---

## ⚙️ Instalasi

### Prerequisites
- Python **3.8 – 3.11** (MediaPipe belum support Python 3.12+)
- OS **Windows** (kontrol audio via pycaw)
- Webcam (internal / eksternal USB)

### Langkah instalasi

**1. Clone repository**
```bash
git clone https://github.com/latifasalsab/Gesture-Volume-Control
cd Gesture Volume Control
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Jalankan program**
```bash
python gesture_volume.py
```

> Jika kamera tidak terbuka, coba ganti `CAM_ID = 1` di baris konfigurasi `gesture_volume.py`

---

## 📁 Struktur File

```
gesture-volume-control/
├── gesture_volume.py       # Program utama
├── HandTrackingModule.py   # Modul deteksi & klasifikasi tangan
├── requirements.txt        # Daftar dependencies
├── README.md               # Dokumentasi ini
└── TUTORIAL.md             # Panduan lengkap & penjelasan kode
```

---

## 🧠 Cara Kerja Sistem

```
Webcam
  ↓
Frame BGR  →  Konversi RGB  →  MediaPipe Hand Detection
                                      ↓
                            21 Landmark Koordinat (x, y)
                                      ↓
                         Hitung jarak & posisi jari
                                      ↓
                         Klasifikasi Gesture
                        ┌──────────┬──────────┐
                     PINCH      FIST      FOUR/PEACE
                        ↓          ↓          ↓
                   Slider Vol  Mute Toggle  ±10% Vol
                        ↓
                   pycaw → Audio System
                        ↓
                   UI Overlay + Dashboard
```

### Konsep utama

- **Landmark detection** — MediaPipe mendeteksi 21 titik koordinat per tangan menggunakan model deep learning
- **Euclidean distance** — Jarak antar landmark dihitung dengan rumus `√((x₂-x₁)² + (y₂-y₁)²)` untuk deteksi pinch
- **EMA Smoothing** — Volume diperhalus dengan Exponential Moving Average `vol = α·input + (1-α)·vol_lama` agar tidak jitter
- **Hold mechanism** — Gesture one-shot membutuhkan konsistensi N frame sebelum aksi dijalankan

---

## 🔧 Konfigurasi

Di bagian atas `gesture_volume.py` terdapat beberapa parameter yang bisa disesuaikan:

```python
CAM_ID      = 0      # ID kamera (0 = default, coba 1 jika tidak terbuka)
CAM_W       = 960    # Lebar frame kamera
CAM_H       = 720    # Tinggi frame kamera
SMOOTHNESS  = 5      # Kelipatan pembulatan volume (lebih besar = lebih kasar)
HOLD_FRAMES = 12     # Frame konsisten sebelum gesture one-shot dijalankan
```

---

## ❗ Troubleshooting

| Error | Solusi |
|---|---|
| `numpy.core.multiarray failed to import` | `pip install "numpy<2" --force-reinstall` |
| `module 'mediapipe' has no attribute 'solutions'` | `pip install mediapipe==0.10.13` |
| `'AudioDevice' has no attribute 'Activate'` | `pip install pycaw==20230407` |
| Kamera tidak terbuka | Ganti `CAM_ID = 1` di konfigurasi |
| Gesture tidak terdeteksi | Pastikan pencahayaan cukup, jarak tangan 30–60 cm |
| `ValueError: dimensions must match` | Sudah otomatis teratasi — sidebar menyesuaikan tinggi frame |

---

## 👩‍💻 Developer

**Latifa** — Teknik Informatika  
Tugas Besar Mata Kuliah Pengolahan Citra  
Semester 6
