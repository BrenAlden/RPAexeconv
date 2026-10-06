import pandas as pd
from pathlib import Path
import os
import glob
import time

base_path = str(Path(__file__).resolve().parents[3])
RLS_CSV_PATH = os.path.join(base_path, "RPA Budget Consumption", "Sources", "ROW LEVEL SECURITY LIST BUDGET DASHBOARD.csv")

def load_rls_mapping(rls_path=RLS_CSV_PATH):
    try:
        df_rls = pd.read_csv(rls_path)
        df_rls.columns = [c.strip() for c in df_rls.columns]
        df_rls['division'] = df_rls['division'].astype(str).str.strip().str.upper()
        df_rls['GROUP1']   = df_rls['GROUP1'].astype(str).str.strip()

        admin_groups       = df_rls[df_rls['division'] == 'ALL']['GROUP1'].unique().tolist()
        non_admin          = df_rls[df_rls['division'] != 'ALL']

        division_to_groups = (
            non_admin.groupby('division')['GROUP1']
            .apply(lambda x: list(x.unique()))
            .to_dict()
        )

        return division_to_groups, admin_groups

    except Exception as e:
        print(f"\n[!] Critical Error: Failed to load RLS CSV → {e}")
        time.sleep(3)
        return None, None

def load_budget_df(input_folder):
    files = glob.glob(os.path.join(input_folder, "*.xlsx"))
    if not files:
        print("\n[!] Error: No Excel files found in the input folder.")
        time.sleep(2)
        return None, None

    latest_file = max(files, key=os.path.getctime)

    try:
        df_raw   = pd.read_excel(latest_file)
        start_row = 0
        for i in range(len(df_raw)):
            row_str = " ".join([str(val) for val in df_raw.iloc[i].values])
            if "Budget" in row_str:
                start_row = i + 1
                break

        df   = pd.read_excel(latest_file, skiprows=start_row)
        cols = df.columns

        col_group  = cols[1]
        col_plan   = cols[3]
        col_actual = cols[4]

        df[col_plan]   = pd.to_numeric(df[col_plan],   errors='coerce').fillna(0)
        df[col_actual] = pd.to_numeric(df[col_actual], errors='coerce').fillna(0)

        df['Current Budget FY'] = df[col_plan].apply(lambda x: round(x, -3))   # ROUND(..., -3)
        df['Actual YTD']        = df[col_actual]
        df['Budget Available']  = df['Current Budget FY'] - df['Actual YTD']

        df = df[~df[col_group].astype(str).str.contains("Total", case=False, na=False)]

        return df, col_group, latest_file

    except Exception as e:
        print(f"\n[!] Gagal memproses file: {e}")
        return None, None, None

def filter_by_division(df, col_group, division, division_to_groups, admin_groups):
    division_upper = division.strip().upper()

    if division_upper == "ALL":
        return df.copy()  

    allowed_groups = division_to_groups.get(division_upper, [])

    if not allowed_groups:
        print(f"\n[!] Warning: Division '{division}' not found in RLS CSV.")
        return pd.DataFrame()  

    return df[df[col_group].isin(allowed_groups)].copy()

def print_group_summary(summary, col_group):
    header = (
        f"{'Group Name':<25} | "
        f"{'Current Budget FY':>22} | "
        f"{'Actual YTD':>22} | "
        f"{'Budget Available':>22} | "
        f"{'% Consumption':>13}"
    )
    print("\nSUMMARY BY DIVISION (GROUP1):")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for _, row in summary.iterrows():
        print(
            f"{str(row[col_group]):<25} | "
            f"IDR {row['Current Budget FY']:>18,.2f} | "
            f"IDR {row['Actual YTD']:>18,.2f} | "
            f"IDR {row['Budget Available']:>18,.2f} | "
            f"{row['% Consumption']:>12.2f}%"
        )
    print("-" * len(header))

def handle_preview_data(input_folder, cmd_logo_func, current_division="ALL"):
    division_to_groups, admin_groups = load_rls_mapping()
    if division_to_groups is None:
        return
    
    result = load_budget_df(input_folder)
    if result[0] is None:
        return
    df, col_group, latest_file = result

    while True:
        cmd_logo_func()
        print(f"PREVIEW DATA - {os.path.basename(latest_file)}")
        print(f"Login sebagai Division : {current_division.upper()}")
        print(" 1. Show Grand Total (Overall Summary)")
        print(" 2. Show Summary by Division (Filtered by RLS)")
        print(" 3. Back to Main Menu")

        choice = input("\nChoose (1-3): ").strip()

        if choice == "1":
            filtered = filter_by_division(df, col_group, current_division,
                                          division_to_groups, admin_groups)

            if filtered.empty:
                print("\n[!] Tidak ada data untuk division ini.")
            else:
                total_plan   = filtered['Current Budget FY'].sum()
                total_actual = filtered['Actual YTD'].sum()
                total_avail  = filtered['Budget Available'].sum()
                total_cons   = (total_actual / total_plan * 100) if total_plan != 0 else 0

                print("\n" + " " * 30 + ">>> GRAND TOTAL SUMMARY <<<")
                print("-" * 105)
                print(f" Division             : {current_division.upper()}")
                print(f" Current Budget FY    : {total_plan:25,.2f} |")
                print(f" Actual YTD           : {total_actual:25,.2f} |")
                print(f" Budget Available     : {total_avail:25,.2f} |")
                print(f" % Consumption        : {(total_cons, 0):29.0f}% |")
                print("-" * 105)

            input("\nPress Enter to return...")

        elif choice == "2":
            filtered = filter_by_division(df, col_group, current_division,
                                          division_to_groups, admin_groups)

            if filtered.empty:
                print("\n[!] No matching data found for the selected division.")
            else:
                summary = filtered.groupby(col_group).agg({
                    'Current Budget FY': 'sum',
                    'Actual YTD':        'sum',
                    'Budget Available':  'sum'
                }).reset_index()

                summary['% Consumption'] = (
                    (summary['Actual YTD'] / summary['Current Budget FY'] * 100)
                    .fillna(0)
                )

                print_group_summary(summary, col_group)

            input("\nPress Enter to return...")

        elif choice == "3":
            break

        else:
            print("\nChoice are not valid!")
            time.sleep(1)

def get_budget_summary(input_folder, current_division="ALL"):
    division_to_groups, admin_groups = load_rls_mapping()
    if division_to_groups is None:
        return None

    result = load_budget_df(input_folder)
    if result[0] is None:
        return None
    df, col_group, _ = result

    filtered = filter_by_division(df, col_group, current_division,
                                  division_to_groups, admin_groups)

    if filtered.empty:
        return pd.DataFrame()

    summary = filtered.groupby(col_group).agg({
        'Current Budget FY': 'sum',
        'Actual YTD':        'sum',
        'Budget Available':  'sum'
    }).reset_index()

    summary['% Consumption'] = (
        (summary['Actual YTD'] / summary['Current Budget FY'] * 100)
        .fillna(0)
    )

    return summary