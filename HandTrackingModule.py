"""
HandTrackingModule.py
=====================
Modul deteksi tangan menggunakan MediaPipe.
Wrapper ini mendeteksi 21 landmark tangan dan menyediakan
berbagai metode untuk analisis gesture.

Landmark reference (nomor titik tangan):
  4  = ujung jempol (thumb tip)
  8  = ujung telunjuk (index tip)
  12 = ujung jari tengah (middle tip)
  16 = ujung jari manis (ring tip)
  20 = ujung kelingking (pinky tip)
"""

import cv2
import math

# MediaPipe 0.10+ menggunakan API baru lewat mediapipe.tasks
# tapi mp.solutions masih tersedia via import eksplisit
import mediapipe.python.solutions.hands as mp_hands_module
import mediapipe.python.solutions.drawing_utils as mp_drawing_module
import mediapipe.python.solutions.drawing_styles as mp_styles_module


class HandDetector:
    """
    Kelas utama untuk deteksi dan analisis tangan.

    Parameters
    ----------
    mode        : static image mode (False = video real-time)
    maxHands    : jumlah tangan maksimum yang dideteksi
    detectionCon: confidence minimum untuk deteksi awal
    trackCon    : confidence minimum untuk tracking
    """

    # Nomor landmark untuk setiap ujung jari
    FINGER_TIPS = [4, 8, 12, 16, 20]
    # Nomor landmark untuk "sendi bawah" tiap jari (untuk cek jari berdiri)
    FINGER_MCP  = [2, 5, 9, 13, 17]

    def __init__(self, mode=False, maxHands=2, detectionCon=0.7, trackCon=0.5):
        self.mode         = mode
        self.maxHands     = maxHands
        self.detectionCon = detectionCon
        self.trackCon     = trackCon

        # Inisialisasi MediaPipe Hands (import eksplisit untuk 0.10+)
        self.mp_hands   = mp_hands_module
        self.hands      = self.mp_hands.Hands(
            static_image_mode        = self.mode,
            max_num_hands            = self.maxHands,
            min_detection_confidence = self.detectionCon,
            min_tracking_confidence  = self.trackCon,
        )
        self.mp_draw    = mp_drawing_module
        self.mp_styles  = mp_styles_module

        self.results    = None   # hasil deteksi MediaPipe
        self.lmList     = []     # daftar landmark tangan pertama
        self.bbox       = []     # bounding box tangan

    # ------------------------------------------------------------------
    # 1. DETEKSI & GAMBAR LANDMARK
    # ------------------------------------------------------------------

    def findHands(self, img, draw=True, flipType=True):
        """
        Proses frame dan opsional gambar skeleton tangan.

        MediaPipe butuh format RGB, sedangkan OpenCV pakai BGR.
        Fungsi ini otomatis mengkonversi warna sebelum proses.

        Returns: img (dengan/tanpa overlay tangan)
        """
        imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(imgRGB)

        if self.results.multi_hand_landmarks and draw:
            for handLms in self.results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    img, handLms,
                    self.mp_hands.HAND_CONNECTIONS,
                    self.mp_styles.get_default_hand_landmarks_style(),
                    self.mp_styles.get_default_hand_connections_style(),
                )
        return img

    def findPosition(self, img, handNo=0, draw=True):
        """
        Ambil koordinat piksel semua 21 landmark tangan.

        Returns
        -------
        lmList : list of [id, x, y]  — koordinat tiap landmark
        bbox   : [xmin, ymin, xmax, ymax] — kotak pembatas tangan
        """
        self.lmList = []
        self.bbox   = []

        if not self.results or not self.results.multi_hand_landmarks:
            return self.lmList, self.bbox

        if handNo >= len(self.results.multi_hand_landmarks):
            return self.lmList, self.bbox

        h, w, _ = img.shape
        myHand  = self.results.multi_hand_landmarks[handNo]

        xList, yList = [], []
        for lm_id, lm in enumerate(myHand.landmark):
            cx, cy = int(lm.x * w), int(lm.y * h)
            self.lmList.append([lm_id, cx, cy])
            xList.append(cx)
            yList.append(cy)

        xmin, xmax = min(xList), max(xList)
        ymin, ymax = min(yList), max(yList)
        # Beri sedikit padding di sekitar tangan
        pad = 20
        self.bbox = [xmin - pad, ymin - pad, xmax + pad, ymax + pad]

        if draw:
            cv2.rectangle(img,
                          (self.bbox[0], self.bbox[1]),
                          (self.bbox[2], self.bbox[3]),
                          (0, 255, 0), 2)

        return self.lmList, self.bbox

    # ------------------------------------------------------------------
    # 2. ANALISIS JARI
    # ------------------------------------------------------------------

    def fingersUp(self):
        """
        Deteksi jari mana yang 'berdiri' (terbuka).

        Logika:
        - Jempol  : bandingkan posisi X (horizontal) karena geraknya ke samping
        - Jari lain: bandingkan posisi Y — ujung jari lebih TINGGI (Y lebih kecil)
                     dari sendi bawahnya = jari berdiri

        Returns: list [thumb, index, middle, ring, pinky]  — 1=berdiri, 0=melipat
        """
        if len(self.lmList) == 0:
            return [0, 0, 0, 0, 0]

        fingers = []

        # Jempol — cek arah X (tangan kanan: tip di kanan MCP = terbuka)
        if self.lmList[4][1] > self.lmList[3][1]:
            fingers.append(1)
        else:
            fingers.append(0)

        # Empat jari lainnya — cek arah Y
        for tip, mcp in zip(self.FINGER_TIPS[1:], self.FINGER_MCP[1:]):
            if self.lmList[tip][2] < self.lmList[mcp][2]:
                fingers.append(1)
            else:
                fingers.append(0)

        return fingers

    def findDistance(self, p1, p2, img=None, draw=True, r=10, t=3):
        """
        Hitung jarak Euclidean antara dua landmark.

        Parameters
        ----------
        p1, p2 : nomor landmark (0-20)
        img    : frame untuk menggambar (opsional)
        draw   : tampilkan garis dan titik di frame

        Returns
        -------
        length   : jarak piksel antara p1 dan p2
        img      : frame (dengan overlay jika draw=True)
        lineInfo : [x1, y1, x2, y2, cx, cy] — koordinat lengkap
        """
        x1, y1 = self.lmList[p1][1], self.lmList[p1][2]
        x2, y2 = self.lmList[p2][1], self.lmList[p2][2]
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        # Rumus jarak Euclidean: sqrt((x2-x1)^2 + (y2-y1)^2)
        length = math.hypot(x2 - x1, y2 - y1)

        if img is not None and draw:
            cv2.line(img,  (x1, y1), (x2, y2), (255, 0, 255), t)
            cv2.circle(img, (x1, y1), r, (255, 0, 255), cv2.FILLED)
            cv2.circle(img, (x2, y2), r, (255, 0, 255), cv2.FILLED)
            cv2.circle(img, (cx, cy), r, (0, 0, 255), cv2.FILLED)

        return length, img, [x1, y1, x2, y2, cx, cy]

    # ------------------------------------------------------------------
    # 3. KLASIFIKASI GESTURE TINGKAT TINGGI
    # ------------------------------------------------------------------

    def classifyGesture(self):
        """
        Klasifikasi gesture tangan menjadi label string.

        Gesture yang didukung:
        - 'PINCH'     : jempol + telunjuk dekat (untuk volume slider)
        - 'FIST'      : semua jari melipat      (mute toggle)
        - 'PEACE'     : telunjuk + jari tengah berdiri (next track)
        - 'OPEN_PALM' : semua jari berdiri      (reset volume 50%)
        - 'THUMBS_UP' : hanya jempol berdiri    (volume +10)
        - 'THUMBS_DOWN': jempol melipat, semua jari melipat (volume -10)
        - 'UNKNOWN'   : gesture tidak dikenali

        Returns: str — nama gesture
        """
        if len(self.lmList) == 0:
            return 'UNKNOWN'

        fingers = self.fingersUp()
        # Hitung jarak jempol-telunjuk untuk deteksi PINCH
        dist_pinch, _, _ = self.findDistance(4, 8, draw=False)

        # PINCH — jempol dan telunjuk berdekatan
        if dist_pinch < 80:
            return 'PINCH'

        # FIST — semua jari melipat
        if fingers == [0, 0, 0, 0, 0]:
            return 'FIST'

        # FOUR — empat jari berdiri (telunjuk+tengah+manis+kelingking), jempol melipat
        if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 1 and fingers[4] == 1:
            return 'THUMBS_UP'

        # PEACE / V — telunjuk + jari tengah berdiri
        if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0:
            return 'PEACE'

        # POINTING — hanya telunjuk berdiri
        if fingers[1] == 1 and fingers[2] == 0 and fingers[3] == 0 and fingers[4] == 0:
            return 'POINTING'

        return 'UNKNOWN'

    # ------------------------------------------------------------------
    # 4. UTILITAS
    # ------------------------------------------------------------------

    def handCount(self):
        """Jumlah tangan yang terdeteksi di frame saat ini."""
        if self.results and self.results.multi_hand_landmarks:
            return len(self.results.multi_hand_landmarks)
        return 0