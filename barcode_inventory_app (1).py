import streamlit as st
import uuid
import qrcode
import os
import json
from datetime import datetime
from openpyxl import Workbook, load_workbook
from PIL import Image, ImageDraw, ImageFont

# ----------------------
# Config & Paths
# ----------------------
APP_BASE_URL = "https://qr-stock-twdxtxesmeefyyewte5uxy.streamlit.app/"

DATA_FILE = "inventory_data.json"
QRCODE_ROOT_DIR = "qrcodes"
REPORTS_DIR = "reports"

os.makedirs(QRCODE_ROOT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ----------------------
# Load / Save Inventory
# ----------------------
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        inventory = json.load(f)
else:
    inventory = {}


def save_inventory():
    with open(DATA_FILE, "w") as f:
        json.dump(inventory, f, indent=4)


# ----------------------
# URL & QR Helpers
# ----------------------
def ensure_app_url() -> str:
    url = APP_BASE_URL.strip()
    if not url.endswith("/"):
        url += "/"
    return url


def generate_qr_images(item_code: str, item_name: str):
    """
    Generate QR code + labeled QR image for an item.
    qrcodes/<item_code>/<item_code>.png
    qrcodes/<item_code>/<item_code>_label.png
    """
    url = ensure_app_url()
    qr_data = f"{url}?code={item_code}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    item_dir = os.path.join(QRCODE_ROOT_DIR, item_code)
    os.makedirs(item_dir, exist_ok=True)

    qr_path = os.path.join(item_dir, f"{item_code}.png")
    qr_img.save(qr_path)

    # Label: QR + text below
    width, height = qr_img.size
    label_height = int(height * 0.45)
    total_height = height + label_height

    label_img = Image.new("RGB", (width, total_height), "white")
    label_img.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(label_img)
    font = ImageFont.load_default()
    text = f"{item_name}\nCode: {item_code}"

    try:
        bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        lines = text.split("\n")
        text_w = max(draw.textlength(line, font=font) for line in lines)
        text_h = len(lines) * (font.size + 4)

    x = (width - text_w) // 2
    y = height + (label_height - text_h) // 2
    draw.multiline_text((x, y), text, fill="black", font=font, align="center")

    label_path = os.path.join(item_dir, f"{item_code}_label.png")
    label_img.save(label_path)

    return qr_path, label_path, qr_data


def get_qr_paths(item_code: str, item_name: str):
    """Ensure QR + label exist for an item."""
    item_dir = os.path.join(QRCODE_ROOT_DIR, item_code)
    qr_path = os.path.join(item_dir, f"{item_code}.png")
    label_path = os.path.join(item_dir, f"{item_code}_label.png")

    if not os.path.exists(qr_path) or not os.path.exists(label_path):
        qr_path, label_path, qr_data = generate_qr_images(item_code, item_name)
    else:
        qr_data = f"{ensure_app_url()}?code={item_code}"

    return qr_path, label_path, qr_data


# ----------------------
# Excel Reporting
# ----------------------
def get_today_report_path() -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(REPORTS_DIR, f"{date_str}_report.xlsx")


def update_excel_report(item_code: str, action: str, qty: int, job: str | None, ts: str):
    """
    Update (or create) today's Excel report.
    Sheet 1: Transactions
    Sheet 2: Stock
    """
    report_path = get_today_report_path()

    if os.path.exists(report_path):
        wb = load_workbook(report_path)
    else:
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Transactions"
        ws1.append(["Time", "Item", "Code", "Action", "Qty", "Job"])
        wb.create_sheet("Stock")

    ws_tx = wb["Transactions"]
    item = inventory[item_code]

    action_label = {
        "in": "IN",
        "out": "OUT",
        "manual": "MANUAL",
    }.get(action, action.upper())

    ws_tx.append([
        ts,
        item.get("name", ""),
        item_code,
        action_label,
        int(qty),
        job or "",
    ])

    # Rebuild Stock sheet for accuracy
    if "Stock" in wb.sheetnames:
        ws_stock = wb["Stock"]
        wb.remove(ws_stock)

    ws_stock = wb.create_sheet("Stock")
    ws_stock.append(["Item", "Code", "Quantity"])

    for code, it in inventory.items():
        ws_stock.append([
            it.get("name", ""),
            code,
            int(it.get("quantity", 0)),
        ])

    wb.save(report_path)


# ----------------------
# Transactions & Item Logic
# ----------------------
def record_transaction(item_code: str, action: str, qty: int, job: str | None = None):
    """Record transaction + update Excel."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "action": action,
        "qty": int(qty),
        "timestamp": ts,
    }
    if job:
        entry["job"] = job

    inventory[item_code].setdefault("history", []).append(entry)
    save_inventory()
    update_excel_report(item_code, action, qty, job, ts)


def show_item_view(item_code: str, header_title: str):
    """Item page with sub-tabs: Transaction, History, Edit, QR."""
    if item_code not in inventory:
        st.error("Item not found.")
        return

    item = inventory[item_code]
    item_name = item.get("name", "")
    qty_current = int(item.get("quantity", 0))

    st.subheader(header_title)

    # Simple header with stock
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.markdown(f"**Item:** {item_name}")
        st.markdown(f"**Code:** `{item_code}`")
    with header_col2:
        color = "green" if qty_current > 0 else "red"
        st.markdown(
            f"<div style='text-align:center; border-radius:8px; padding:8px; "
            f"border:1px solid #DDD;'><div style='font-size:12px;color:#555;'>Stock</div>"
            f"<div style='font-size:22px;font-weight:bold;color:{color};'>{qty_current}</div></div>",
            unsafe_allow_html=True,
        )

    tab_tx, tab_hist, tab_edit, tab_qr = st.tabs(
        ["💼 Transaction", "📜 History", "✏️ Edit", "🖨️ QR Code"]
    )

    # ------------- Transaction Tab -------------
    with tab_tx:
        st.markdown("##### Transaction")

        tx_box = st.container()
        with tx_box:
            col_tx1, col_tx2 = st.columns(2)
            with col_tx1:
                action = st.selectbox(
                    "Action",
                    ["Check In", "Check Out"],
                    key=f"tx_action_{item_code}",
                )
            with col_tx2:
                qty = st.number_input(
                    "Quantity",
                    min_value=1,
                    step=1,
                    key=f"tx_qty_{item_code}",
                )

            job = None
            if action == "Check Out":
                job = st.text_input(
                    "Job / Project (optional)",
                    key=f"tx_job_{item_code}",
                )

            st.markdown("")
            if st.button("Apply Transaction", type="primary", key=f"tx_save_{item_code}"):
                if action == "Check Out" and qty > qty_current:
                    st.error("Cannot check out more items than are in stock.")
                else:
                    if action == "Check In":
                        inventory[item_code]["quantity"] = qty_current + int(qty)
                        save_inventory()
                        record_transaction(item_code, "in", qty)
                        st.success(f"Checked IN {qty} item(s).")
                    else:
                        inventory[item_code]["quantity"] = qty_current - int(qty)
                        save_inventory()
                        record_transaction(item_code, "out", qty, job)
                        st.success(f"Checked OUT {qty} item(s).")

                    st.rerun()

    # ------------- History Tab -------------
    with tab_hist:
        st.markdown("##### History")
        history = item.get("history", [])
        if not history:
            st.info("No transactions recorded yet.")
        else:
            rows = []
            for entry in reversed(history):
                rows.append({
                    "Time": entry.get("timestamp", ""),
                    "Action": {
                        "in": "IN",
                        "out": "OUT",
                        "manual": "MANUAL",
                    }.get(entry.get("action"), entry.get("action", "").upper()),
                    "Qty": entry.get("qty", 0),
                    "Job": entry.get("job", ""),
                })
            st.dataframe(rows, use_container_width=True)

    # ------------- Edit Tab -------------
    with tab_edit:
        st.markdown("##### Edit Item")

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            edit_name = st.text_input(
                "Item Name",
                value=item_name,
                key=f"edit_name_{item_code}",
            )
            edit_code = st.text_input(
                "Item Code",
                value=item_code,
                key=f"edit_code_{item_code}",
            )
        with col_e2:
            edit_qty = st.number_input(
                "Quantity (manual override)",
                min_value=0,
                value=qty_current,
                step=1,
                key=f"edit_qty_{item_code}",
            )

        if st.button("Save Changes", type="primary", key=f"edit_save_{item_code}"):
            code_changed = (edit_code != item_code)
            name_changed = (edit_name != item_name)
            qty_changed = (edit_qty != qty_current)

            new_code = item_code

            # Code change
            if code_changed:
                if edit_code in inventory and edit_code != item_code:
                    st.error(f"Item code '{edit_code}' already exists. Choose another code.")
                    return
                new_code = edit_code
                inventory[new_code] = inventory.pop(item_code)
                item = inventory[new_code]

            # Name change
            if name_changed:
                item["name"] = edit_name

            # Quantity change
            if qty_changed:
                diff = int(edit_qty) - qty_current
                item["quantity"] = int(edit_qty)
                save_inventory()
                if diff != 0:
                    record_transaction(
                        new_code,
                        "manual",
                        abs(diff),
                        job=f"Manual adjust from {qty_current} to {edit_qty}",
                    )

            save_inventory()

            # Regenerate QR label if name or code changed
            if code_changed or name_changed:
                _, label_path, _ = generate_qr_images(new_code, edit_name)
                st.success("Item updated and QR label regenerated.")
                st.image(label_path, caption="Updated QR label")
            else:
                st.success("Item updated.")

            st.rerun()

    # ------------- QR Tab -------------
    with tab_qr:
        st.markdown("##### QR Code")

        qr_path, label_path, qr_data = get_qr_paths(item_code, item_name)

        if os.path.exists(label_path):
            st.image(label_path, caption="QR Label")
        else:
            st.info("QR label will be created when needed.")

        col_q1, col_q2 = st.columns(2)
        if os.path.exists(qr_path):
            with col_q1:
                with open(qr_path, "rb") as f_qr:
                    st.download_button(
                        "Download QR (PNG)",
                        data=f_qr,
                        file_name=f"{item_code}_qr.png",
                        mime="image/png",
                        key=f"dl_qr_{item_code}",
                    )
        if os.path.exists(label_path):
            with col_q2:
                with open(label_path, "rb") as f_lbl:
                    st.download_button(
                        "Download Label (PNG)",
                        data=f_lbl,
                        file_name=f"{item_code}_label.png",
                        mime="image/png",
                        key=f"dl_label_{item_code}",
                    )

        st.caption("Scan this QR with your phone camera to open this item directly.")
        st.code(qr_data, language="text")


# ----------------------
# Streamlit App Layout
# ----------------------
st.set_page_config(page_title="QR Stock", page_icon="📦", layout="centered")

st.markdown(
    "<h2 style='margin-bottom:0.2rem;'>QR Stock</h2>"
    "<div style='color:#666;margin-bottom:1rem;'>QR-based inventory for tools and parts.</div>",
    unsafe_allow_html=True,
)

# Detect QR param
scanned_code = None
qp = st.query_params
if "code" in qp and qp["code"]:
    val = qp["code"]
    scanned_code = val[0] if isinstance(val, list) else val

# Page state
PAGES = ["Home", "Item", "Admin"]
if "page" not in st.session_state:
    st.session_state["page"] = "Home"

# If opened via QR, default to Item page once
if scanned_code and st.session_state.get("page_init_qr") is None:
    st.session_state["page"] = "Item"
    st.session_state["page_init_qr"] = True

current_index = PAGES.index(st.session_state["page"])
page = st.radio(
    "Page",
    PAGES,
    index=current_index,
    horizontal=True,
    label_visibility="collapsed",
)
st.session_state["page"] = page

# ----------------------
# HOME PAGE
# ----------------------
if page == "Home":
    st.subheader("Overview")

    st.markdown("#### Today's Excel Report")
    today_report = get_today_report_path()
    if os.path.exists(today_report):
        with open(today_report, "rb") as f:
            st.download_button(
                "Download Today's Report",
                data=f,
                file_name=os.path.basename(today_report),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_report_home",
            )
    else:
        st.caption("No transactions recorded today yet.")

    st.markdown("#### Quick Guide")
    st.markdown(
        "- Use **Admin** to create items and generate QR labels.\n"
        "- Stick QR labels on shelves, bins, or tools.\n"
        "- Workers scan QR with phone camera to open the **Item** page.\n"
        "- Use **Transaction** tab to check stock in or out.\n"
    )

# ----------------------
# ITEM PAGE
# ----------------------
elif page == "Item":
    st.subheader("Item")

    item_to_show = None

    # QR-scan case
    if scanned_code:
        if scanned_code in inventory:
            item_to_show = scanned_code
            st.caption(f"Loaded via QR code: `{scanned_code}`")
        else:
            st.error("Scanned item code not found in inventory.")

    # Manual selection
    if not scanned_code:
        if not inventory:
            st.info("No items yet. Use Admin to add items.")
        else:
            st.markdown("#### Select Item")
            items = []
            for code, it in sorted(inventory.items(), key=lambda x: x[1].get("name", "").lower()):
                label = f"{it.get('name','')} ({code})"
                items.append((label, code))

            labels = [label for (label, _) in items]
            labels_by_code = {label: code for (label, code) in items}

            placeholder = "[Select item]"
            ui_options = [placeholder] + labels

            selected_label = st.selectbox(
                "",
                ui_options,
                index=0,
            )

            if selected_label != placeholder:
                item_to_show = labels_by_code[selected_label]

    if item_to_show:
        show_item_view(item_to_show, header_title="Item Overview")

# ----------------------
# ADMIN PAGE
# ----------------------
elif page == "Admin":
    st.subheader("Admin")

    st.markdown("#### Create New Item & QR Label")

    col_a1, col_a2 = st.columns(2)
    with col_a1:
        item_name = st.text_input("Item Name")
    with col_a2:
        item_code_input = st.text_input("Item Code (optional)")

    if st.button("Create Item & Generate QR Label", type="primary"):
        if not item_name:
            st.error("Please enter an item name.")
        else:
            item_code = item_code_input.strip() or str(uuid.uuid4())[:8]

            if item_code in inventory:
                st.warning(f"Item code '{item_code}' already exists. Using existing item.")
            else:
                inventory[item_code] = {
                    "name": item_name,
                    "quantity": 0,
                    "history": [],
                }
                save_inventory()

            qr_path, label_path, qr_data = generate_qr_images(item_code, item_name)

            st.success(f"Item '{item_name}' saved with code `{item_code}`.")
            st.image(label_path, caption="QR label")

            col_d1, col_d2 = st.columns(2)
            if os.path.exists(qr_path):
                with col_d1:
                    with open(qr_path, "rb") as f_qr:
                        st.download_button(
                            "Download QR (PNG)",
                            data=f_qr,
                            file_name=f"{item_code}_qr.png",
                            mime="image/png",
                            key=f"dl_qr_new_{item_code}",
                        )
            if os.path.exists(label_path):
                with col_d2:
                    with open(label_path, "rb") as f_lbl:
                        st.download_button(
                            "Download Label (PNG)",
                            data=f_lbl,
                            file_name=f"{item_code}_label.png",
                            mime="image/png",
                            key=f"dl_label_new_{item_code}",
                        )

            st.code(qr_data, language="text")

    st.markdown("---")
    st.markdown("#### Today's Excel Report")

    today_report = get_today_report_path()
    if os.path.exists(today_report):
        with open(today_report, "rb") as f:
            st.download_button(
                "Download Today's Report",
                data=f,
                file_name=os.path.basename(today_report),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_report_admin",
            )
    else:
        st.caption("No transactions recorded today yet.")
