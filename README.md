# Hotel Reviews Data Ingestion Pipeline

Pipeline otomatisasi *data ingestion* yang menarik dataset ulasan hotel dari server MinIO VPS melalui FastAPI (**Hotel Reviews Intake API**) dan menyimpannya ke **Azure Blob Storage** secara terjadwal maupun manual menggunakan **Azure Functions (Python v2)** serta **GitHub Actions CI/CD**.

---

## Arsitektur & Komponen Sistem

* **Sumber Data (Source API):** `https://upload-data-hotel.duckdns.org`
  * `GET /api/uploads` — Mengambil daftar metadata file dataset yang tersedia.
  * `GET /api/uploads/{id}/download` — Mengunduh file CSV dari MinIO VPS (memerlukan otorisasi token).
* **Compute (Azure Function App):** `hotel-review`
  * **Resource Group:** `rg-hotel-review-prod`
  * **Region:** `East Asia`
  * **OS & Runtime:** Linux — Python `3.11` (App Service Plan `B1`)
  * **Fungsi Aktif:**
    1. `hotel_reviews_scheduler` (**Timer Trigger**): Berjalan otomatis setiap 6 jam (`0 0 */6 * * *`).
    2. `manual_trigger_ingestion` (**HTTP Trigger**): Endpoint `/api/trigger-ingestion` (`AuthLevel.FUNCTION`) untuk memicu *ingestion* secara manual.
* **Data Store (Azure Blob Storage):**
  * **Storage Account:** gunakan nama Storage Account yang dibuat untuk proyek ini.
  * **Container:** `hotel-reviews-ingested` (data tersimpan rapi per direktori `batch_YYYYMMDD_HHMMSS/`).
* **CI/CD Automation:** GitHub Actions (`.github/workflows/ci-cd-pipeline.yaml`)
  * **CI - Lint & Unit Test:** Validasi sintaks dengan `flake8` dan pengujian unit dengan `pytest`.
  * **CD - Deploy to Azure Function App:** *Deployment* otomatis ke `hotel-review` setelah *push* atau *merge* ke branch `main`, jika CI berhasil.
  * CI juga berjalan pada Pull Request ke `main`; proses deploy hanya berjalan dari `main`.
* **Jadwal ingestion:** Azure Functions Timer Trigger berjalan setiap 6 jam (`0 0 */6 * * *`, zona waktu UTC). Jadwal ingestion terpisah dari GitHub Actions agar jadwal tidak menyebabkan deployment berulang.

---

## Struktur Direktori Repositori

```text
ci-cd-ingest/
├── .github/
│   └── workflows/
│       └── ci-cd-pipeline.yaml   # Konfigurasi pipeline CI/CD GitHub Actions
├── tests/                        # Unit test untuk pengujian otomatis (pytest)
├── function_app.py               # Kode utama Azure Functions v2 (Timer & HTTP Trigger)
├── host.json                     # Konfigurasi runtime Azure Functions v2 & Extension Bundle
├── requirements.txt              # Daftar dependensi Python (termasuk pin cryptography==42.0.8)
├── .gitignore                    # Mengabaikan kredensial lokal, cache, dan environment
└── README.md                     # Dokumentasi setup, kolaborasi Git, dan verifikasi
```

---

## Prasyarat (Prerequisites)

Sebelum menjalankan proyek di komputer lokal, pastikan perangkat Anda sudah terpasang:

* **Python 3.11** (sesuai versi runtime di Azure Linux App Service)
* **Git**
* **Azure Functions Core Tools v4** *(opsional, jika ingin menjalankan fungsi secara lokal melalui terminal)*
* **Kredensial rahasia proyek** — Mintalah nilai `API_AUTH_TOKEN` dan `AZURE_STORAGE_CONNECTION_STRING` kepada pengelola repositori. **Jangan pernah meng-commit kredensial ke GitHub.**

---

## Panduan Setup & Menjalankan Secara Lokal

### 1. Clone Repositori

```bash
git clone https://github.com/kayistar/cicd-ingestion.git
cd cicd-ingestion
```

### 2. Buat & Aktifkan Virtual Environment

* **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
* **Linux / macOS:**
  ```bash
  python3.11 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Dependensi

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Catatan:** Paket `cryptography==42.0.8` dikunci secara eksplisit di `requirements.txt` untuk menjaga kompatibilitas GLIBC pada container Linux Debian di Azure App Service.

### 4. Konfigurasi Variabel Lingkungan Lokal (`local.settings.json`)

Buat file `local.settings.json` di direktori utama proyek (file ini otomatis diabaikan oleh `.gitignore`), lalu isi dengan struktur berikut:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    "API_BASE_URL": "https://upload-data-hotel.duckdns.org",
    "API_AUTH_TOKEN": "MASUKKAN_TOKEN_OTORISASI_API_DI_SINI",
    "AZURE_STORAGE_CONNECTION_STRING": "MASUKKAN_CONNECTION_STRING_STORAGE_DI_SINI"
  }
}
```

### 5. Jalankan Linter, Unit Test, & Fungsi Lokal

Pastikan kode bebas dari error sebelum di-push ke GitHub:

```bash
# Cek gaya penulisan & sintaks kode
flake8 function_app.py tests --count --select=E9,F63,F7,F82 --show-source --statistics

# Jalankan unit test
pytest

# (Opsional) Jalankan Azure Functions secara lokal
func start
```

> Jika `func start` dijalankan, Anda dapat menguji trigger manual melalui browser atau `curl` ke `http://localhost:7071/api/trigger-ingestion`.

### Konfigurasi resource Azure dan GitHub

Pastikan Function App memiliki application settings berikut melalui **Azure Portal → Function App → Settings → Environment variables**:

* `AzureWebJobsStorage` — connection string storage yang digunakan Azure Functions untuk runtime dan timer trigger.
* `AzureWebJobsFeatureFlags` — `EnableWorkerIndexing` untuk model Python v2.
* `API_BASE_URL` — `https://upload-data-hotel.duckdns.org`.
* `API_AUTH_TOKEN` — token akses API dari pengelola sumber data.
* `AZURE_STORAGE_CONNECTION_STRING` — connection string Storage Account tujuan.

Untuk mengaktifkan deployment GitHub Actions, simpan publish profile Function App sebagai GitHub Actions secret bernama `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` (**Settings → Secrets and variables → Actions**). Jangan masukkan token atau connection string ke source code, README, screenshot, maupun commit.

Nama resource Azure pada panduan ini mengikuti konfigurasi proyek. Jika resource tersebut belum ada atau tidak dapat diakses di subscription Anda, buat resource yang sesuai dan perbarui nama di workflow serta dokumentasi.

---

## Alur Kolaborasi Git & CI/CD Deployment

1. **Tarik Pembaruan Terbaru dari `main`:**
   ```bash
   git checkout main
   git pull origin main
   ```
2. **Buat Branch Fitur Baru:**
   ```bash
   git checkout -b feat/nama-perubahan
   ```
3. **Commit & Push ke Branch Fitur:**
   ```bash
   git add .
   git commit -m "feat: deskripsi singkat perubahan"
   git push origin feat/nama-perubahan
   ```
4. **Buat Pull Request (PR):**
   * Buka repositori di GitHub, lalu buat **Pull Request** dari branch fitur Anda menuju `main`.
   * Workflow **CI-CD Hotel Reviews Ingestion Pipeline** menjalankan lint dan unit test pada PR.
   * Setelah PR di-review dan di-merge ke `main`, workflow berjalan kembali; jika CI berhasil, versi terbaru di-deploy ke Function App `hotel-review` menggunakan secret `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`.

### Skenario Git untuk bukti tugas

Jalankan langkah berikut dari PowerShell di folder repository untuk menunjukkan proses branch, commit, push, PR, dan merge. Perintah ini memasukkan perubahan proyek yang sedang dikerjakan ke branch fitur:

```powershell
git status
git switch -c feat/hotel-reviews-ingestion-ci-cd
git add .gitignore .github/workflows/ci-cd-pipeline.yaml README.md function_app.py tests/test_pipeline.py
git commit -m "feat: complete hotel reviews ingestion CI/CD"
git push -u origin feat/hotel-reviews-ingestion-ci-cd
```

Buat Pull Request dari `feat/hotel-reviews-ingestion-ci-cd` ke `main` di GitHub. Simpan bukti PR dan CI yang berhasil, lalu merge PR dan simpan bukti merge serta deployment pada tab **Actions**.

### Checklist screenshot untuk laporan PDF

Susun screenshot dan keterangan singkat sesuai urutan proses:

1. Struktur repository dan kode Python `function_app.py` (sensor/sembunyikan semua token dan connection string).
2. Branch fitur, perubahan/commit, dan hasil `git push`.
3. Pull Request dari branch fitur ke `main`.
4. CI pada PR: tahapan lint dan unit test berhasil.
5. PR yang sudah di-merge ke `main`.
6. GitHub Actions: job deployment berhasil.
7. Dekorator Timer Trigger dengan cron `0 0 */6 * * *` dan pengaturan trigger di Azure.
8. HTTP Trigger manual berhasil dengan respons `200`.
9. Azure Blob container `hotel-reviews-ingested` berisi file CSV pada direktori batch.
10. Resource Function App dan Storage Account di Azure Portal.

Nama berkas akhir: `CI-CD_[Class]_[NIM]_[Name].pdf`. Jadwal timer menggunakan UTC; screenshot `Run workflow` hanya membuktikan eksekusi workflow GitHub, bukan jadwal otomatis Azure Timer.

---

## Verifikasi di Portal Azure

### 1. Pengujian Manual Pipeline (`manual_trigger_ingestion`)

1. Buka **Portal Azure** → **Resource Group** `rg-hotel-review-prod` → **Function App** `hotel-review`.
2. Pada bagian **Functions**, klik `manual_trigger_ingestion` → masuk ke menu **Code + Test**.
3. Klik **Test/Run** → **Run**.
4. Pastikan panel **Output** menampilkan **HTTP response code: `200 OK`** beserta JSON ringkasan daftar file CSV yang berhasil diunduh dan diunggah.

### 2. Verifikasi File CSV di Azure Blob Storage

1. Buka Storage Account yang connection string-nya disimpan sebagai `AZURE_STORAGE_CONNECTION_STRING` di Function App.
2. Masuk ke menu **Data storage** → **Containers** → klik container `hotel-reviews-ingested`.
3. Jika muncul pemberitahuan izin Microsoft Entra ID, klik tautan **(Switch to Access key)** di bagian atas daftar blob.
4. Buka folder `batch_YYYYMMDD_HHMMSS/` terbaru untuk memastikan seluruh file CSV dari MinIO VPS telah tersimpan dengan ukuran file yang valid.
