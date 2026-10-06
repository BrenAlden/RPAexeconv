import pandas as pd
import win32com.client as win32
from pathlib import Path
import os
from datetime import datetime

def send_budget_emails(summary_df):
    base_path = str(Path(__file__).resolve().parents[3])
    mapping_path = os.path.join(base_path, "Output RPA Budget Consumption", "Preference", "Group to Division.xlsx")
    master_email_path = os.path.join(base_path, "Output RPA Budget Consumption", "Preference", "Master Email.xlsm")
    template_path = os.path.join(base_path, "RPA Budget Consumption", "Templates", "email_templates.html")

    now = datetime.now()
    curr_month_name = now.strftime('%B')
    curr_year = now.strftime('%Y')

    try:
        # Load Master Email
        xl = pd.ExcelFile(master_email_path)
        target_sheet = next((s for s in xl.sheet_names if any(k in s.lower() for k in ['email', 'master'])), xl.sheet_names[0])

        df_raw = pd.read_excel(master_email_path, sheet_name=target_sheet, header=None)
        master_skip = 0
        for i, row in df_raw.iterrows():
            if any("divisi" in str(s).lower() for s in row.values):
                master_skip = i
                break

        df_master = pd.read_excel(master_email_path, sheet_name=target_sheet, skiprows=master_skip)
        df_master.columns = [str(c).strip() for c in df_master.columns]

        col_div_master   = next((c for c in df_master.columns if 'divisi' in c.lower()), None)
        col_email_master = next((c for c in df_master.columns if 'email' in c.lower()), None)
        col_cc_master    = next((c for c in df_master.columns if 'cc' in c.lower()), None)

        # Load Mapping & Merge
        # Load Mapping & Merge
        df_map = pd.read_excel(mapping_path)
        df_map.columns = [str(c).strip() for c in df_map.columns]
        df_map['Group1'] = df_map.iloc[:, 2].astype(str).str.strip()
        summary_df.columns = [str(c).strip() for c in summary_df.columns]

        col_budget_id = summary_df.columns[0]
        summary_df[col_budget_id] = summary_df[col_budget_id].astype(str).str.strip().str.upper()
        df_map['Group1'] = df_map['Group1'].astype(str).str.strip().str.upper()

        df_merged = pd.merge(summary_df, df_map, left_on=col_budget_id, right_on='Group1', how='inner')
        print(f"[*] Merged Rows (Setelah Upper): {len(df_merged)}")

        if df_merged.empty:
            print("[!] HASIL MERGE TETAP 0. Cek apakah ID di file Budget vs Mapping sudah sama.")
            return

        # Grouping
        b_cols = summary_df.columns[1:4]
        div_summary = df_merged.groupby('Group1_Text').agg({
            b_cols[0]: 'sum', b_cols[1]: 'sum', b_cols[2]: 'sum'
        }).reset_index()
        div_summary['% Consumption'] = (div_summary[b_cols[1]] / div_summary[b_cols[0]] * 100).fillna(0)

        # Filter out zero rows dulu sebelum tampil ke user
        div_valid = div_summary[
            ~((div_summary[b_cols[0]] == 0) & (div_summary[b_cols[1]] == 0) & (div_summary[b_cols[2]] == 0))
        ].reset_index(drop=True)

        skipped_zero = len(div_summary) - len(div_valid)
        if skipped_zero > 0:
            print(f"[INFO] {skipped_zero} divisi diskip karena semua nilai 0.")

        if div_valid.empty:
            print("[!] Tidak ada divisi dengan data valid untuk dikirim.")
            return

        print("\nPilih mode pengiriman email:")
        print("  1. Kirim ke semua divisi")
        print("  2. Kirim ke 1 divisi")
        mode_choice = input("Pilihan (1/2): ").strip()

        if mode_choice == "2":
            print("\nDaftar divisi yang tersedia:")
            for idx, nama in enumerate(div_valid['Group1_Text'], start=1):
                print(f"  {idx}. {nama}")

            while True:
                pilihan = input("\nMasukkan nomor divisi yang ingin dikirim: ").strip()
                if pilihan.isdigit() and 1 <= int(pilihan) <= len(div_valid):
                    selected_idx = int(pilihan) - 1
                    selected_name = div_valid.loc[selected_idx, 'Group1_Text']
                    print(f"[*] Akan mengirim ke: {selected_name}")
                    confirm = input("Konfirmasi? (y/n): ").strip().lower()
                    if confirm == 'y':
                        div_valid = div_valid[div_valid.index == selected_idx]
                        break
                    else:
                        print("[*] Dibatalkan, silakan pilih ulang.")
                else:
                    print(f"[!] Input tidak valid. Masukkan angka 1–{len(div_valid)}.")

        elif mode_choice == "1":
            print(f"[*] Akan mengirim ke semua {len(div_valid)} divisi.")
            confirm = input("Konfirmasi? (y/n): ").strip().lower()
            if confirm != 'y':
                print("[*] Pengiriman dibatalkan.")
                return
        else:
            print("[!] Pilihan tidak valid. Pengiriman dibatalkan.")
            return
        # ────────────────────────────────────────────────────────────────────

        outlook = win32.Dispatch('outlook.application')
        with open(template_path, 'r') as f:
            html_content = f.read()

        sent_count      = 0
        skipped_noemail = 0

        for _, row in div_valid.iterrows():
            nama_lookup = str(row['Group1_Text']).strip()

            match = df_master[
                df_master[col_div_master].astype(str).str.strip().str.lower() == nama_lookup.lower()
            ]

            if not match.empty:
                recipient = str(match[col_email_master].iloc[0]).strip()
                cc_target = str(match[col_cc_master].iloc[0]).strip() if col_cc_master and pd.notna(match[col_cc_master].iloc[0]) else ""

                body = html_content.replace("{{month}}", curr_month_name)\
                                   .replace("{{year}}", curr_year)\
                                   .replace("{{adm_division}}", nama_lookup)\
                                   .replace("{{curr_budget}}", f"{row[b_cols[0]] / 1_000_000:,.0f}")\
                                   .replace("{{actl_budget}}", f"{row[b_cols[1]] / 1_000_000:,.0f}")\
                                   .replace("{{budget_avail}}", f"{row[b_cols[2]] / 1_000_000:,.0f}")\
                                   .replace("{{pctg_consumption}}", f"{row['% Consumption']:.2f}%")

                mail = outlook.CreateItem(0)
                mail.To = recipient
                if cc_target:
                    mail.CC = cc_target
                mail.Subject = f"Opex/FOH Division Budget Consumption / {nama_lookup}"
                mail.HTMLBody = body
                mail.Send()
                print(f"[SUCCESS] Sent to {nama_lookup}")
                sent_count += 1
            else:
                print(f"[!] Email tidak ditemukan untuk: {nama_lookup}")
                skipped_noemail += 1

        print(f"\n[SUMMARY] Terkirim: {sent_count} | Diskip (zero): {skipped_zero} | Tidak ada email: {skipped_noemail}")

    except Exception as e:
        print(f"[!] Error: {str(e)}")