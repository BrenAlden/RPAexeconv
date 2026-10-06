# RPA EXE Converter

Package folder proyek Python RPA menjadi satu file `.exe` Windows onefile
yang siap dijalankan sekali klik, lengkap dengan GUI launcher (Start/Stop,
panel log real-time, folder `input/` dan `output/` di sebelah exe).

## Ringkasan

Hasil build punya bentuk:

```
<output_folder>/
├── RPA_<nama_project>.exe
├── input/
└── output/
```

`input/` dan `output/` dibuat otomatis oleh launcher saat exe pertama kali
dijalankan. Path-nya dihitung dari `sys.executable` (bukan `_MEIPASS`), jadi
aman meski dipindahkan.

## Struktur repo

```
ExeConv/
├── execonv.py                     # entry CLI / launcher GUI converter
├── converter/
│   ├── __init__.py
│   ├── scanner.py                 # walk folder, kumpulkan .py + aset
│   ├── entrypoint_detector.py     # AST-based main-guard detection
│   ├── dependency_resolver.py     # klasifikasi lokal / stdlib / third-party
│   ├── wrapper_generator.py       # generate launcher tkinter
│   ├── builder.py                 # invoke PyInstaller onefile
│   └── ui.py                      # GUI converter
├── sample_rpa/                    # proyek dummy untuk uji coba
│   ├── main.py
│   ├── config.py
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── requirements.txt
└── README.md
```

## Prasyarat

- Windows 10 / 11
- Python 3.10 atau lebih baru
- `pip install -r requirements.txt` (pyinstaller)
- Semua dependency **proyek RPA target** juga harus ter-install di lingkungan
  yang sama saat build (mis. `pandas`, `selenium`, dst.). Rekomendasi: pakai
  virtualenv per-proyek.

## Cara pakai

### Mode GUI (default)

```powershell
python execonv.py
```

1. Klik **Browse...** pada baris *Project folder*, pilih folder proyek RPA.
2. Converter scan otomatis. Dropdown *Entry point* akan terisi kandidat file
   yang punya `if __name__ == "__main__":`. Pilih yang benar (biasanya
   `main.py` atau `Codes/Main.py`).
3. (Opsional) pilih file `.ico` untuk icon exe.
4. (Opsional) ubah *Output folder*. Default: `<parent>/RPA_<nama>_dist`.
5. Klik **Build EXE**. Log build streaming ke panel bawah.
6. Selesai — klik **Open Output Folder**.

### Mode CLI (headless)

```powershell
python execonv.py --project "C:\path\ke\proyek" --output "C:\out"
```

Opsi tambahan:
- `--entry <module>`  : paksa modul tertentu (mis. `Main`). Kalau tidak
  di-set, converter auto-pick berdasarkan prioritas.
- `--icon <file.ico>` : icon exe.
- `-v`                : log DEBUG.

### Uji coba dengan sample project

```powershell
# Build sample
python execonv.py --project sample_rpa --output dist_sample

# Jalankan hasil
.\dist_sample\RPA_sample_rpa.exe
```

Klik **Start** di launcher. Sample akan bikin `input/hello.txt` kalau
kosong. Isi ulang file di `input/`, klik Start lagi, hasilnya muncul di
`output/`.

## Bagaimana launcher yang di-generate bekerja

Wrapper pakai pola **self-relaunch**:

```
[double-click exe]
      │
      ▼
┌─────────────┐  spawn subprocess  ┌────────────────────┐
│ GUI parent  │ ─────────────────▶ │ child --run-rpa    │
│ tkinter     │ ◀── stdout/stderr  │ runpy.run_module() │
└─────────────┘                    └────────────────────┘
```

Manfaat:
- Tombol **Stop** benar-benar mematikan proses RPA lewat `Popen.kill()`.
- Output `print()` dari kode RPA muncul di panel log real-time.
- GUI tidak freeze meski RPA sibuk (mis. `selenium` menunggu).

Env var yang diberikan ke kode RPA:
- `RPA_INPUT_DIR`  — path absolut folder `input/`
- `RPA_OUTPUT_DIR` — path absolut folder `output/`
- `RPA_EXE_DIR`   — path absolut folder exe
- CWD juga di-`chdir` ke folder exe.

**Rekomendasi untuk kode RPA:** pakai env var di atas dan/atau
`sys.executable` (saat `sys.frozen`), bukan `Path(__file__)`, karena
dalam mode onefile `__file__` mengarah ke direktori temp `_MEIPASS`
yang tidak stabil.

Contoh pola yang aman:

```python
import os, sys
from pathlib import Path

def rpa_home() -> Path:
    if os.environ.get("RPA_EXE_DIR"):
        return Path(os.environ["RPA_EXE_DIR"])
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
```

## Catatan batasan / kendala

- **Semantik `__file__` berubah di mode onefile.** Kode RPA yang menghitung
  path dari `Path(__file__).parents[N]` akan tetap "berjalan" tapi menunjuk
  ke folder temp. Gunakan env var launcher atau `sys.executable`.
- **Antivirus false positive.** Executable PyInstaller onefile kadang
  di-flag oleh Windows Defender atau AV korporat. Kalau kena, opsi:
  a) build ulang setelah update PyInstaller,
  b) pindah ke `--onedir` (belum didukung di converter ini),
  c) code-sign hasil exe.
- **Ukuran exe.** Bundle onefile untuk proyek yang butuh `pandas`,
  `numpy`, `selenium` biasanya 60–150 MB. Wajar untuk PyInstaller.
- **Startup lambat.** Onefile perlu extract ke temp saat run pertama
  di setiap sesi. Setelah cache siap, run berikutnya lebih cepat.
- **Dependency tersembunyi.** Beberapa paket dipakai secara transitif
  (mis. `openpyxl` via `pandas.read_excel`) atau punya nama distribusi
  beda dengan nama import (`pywin32` -> `win32com`). Converter otomatis
  augment hidden imports dari `requirements.txt` di root proyek dan
  mengaplikasikan mapping alias standar; kalau masih kurang, tambahkan
  via kode `BuildOptions.extra_hidden_imports`.
- **Semua dependency pihak-ketiga harus ter-install di lingkungan
  build.** PyInstaller mem-freeze library dari `site-packages` Python
  yang menjalankannya, bukan dari `requirements.txt`.
- **Path dengan spasi / karakter khusus.** Sudah di-handle: converter
  copy proyek ke workspace temp dan mengirim semua argumen sebagai list
  ke `subprocess.Popen` (bukan string interpolasi shell).
- **Windows-only.** Target hanya `.exe` Windows. Untuk cross-compile ke
  Linux/macOS, jalankan converter di OS target-nya.

## Troubleshooting singkat

| Masalah                                       | Solusi                                                          |
|-----------------------------------------------|-----------------------------------------------------------------|
| "PyInstaller tidak tersedia"                  | `pip install pyinstaller` di interpreter yang sama              |
| "Tidak ada file dengan `if __name__ == ...`"  | Tambahkan blok tersebut ke file utama proyek                    |
| Build sukses tapi exe error `ModuleNotFound`  | Tambah nama modul ke `extra_hidden_imports`                     |
| exe kena antivirus                            | Lihat "Catatan batasan" di atas                                 |
| Path input/output salah saat frozen           | Ganti `Path(__file__)` dengan env var `RPA_INPUT_DIR`, dst.     |
