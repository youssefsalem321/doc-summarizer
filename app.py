"""واجهة Streamlit:  streamlit run app.py"""
import streamlit as st

from summarizer import load_text, summarize_contract, summarize_email

st.set_page_config(page_title="ملخّص الإيميلات والعقود", page_icon="📄")
st.title("📄 ملخّص الإيميلات والعقود")

kind = st.radio("نوع المستند", ["إيميل", "عقد"], horizontal=True)
uploaded = st.file_uploader("ارفع ملف (PDF / DOCX / TXT)", type=["pdf", "docx", "txt", "eml"])
pasted = st.text_area("أو الصق النص هنا", height=200)

if kind == "عقد":
    st.warning(
        "⚠️ الملخص للفهم السريع فقط وليس استشارة قانونية. "
        "راجع العقد الأصلي أو محامي قبل أي قرار."
    )

if st.button("لخّص", type="primary"):
    try:
        text = load_text(uploaded.getvalue(), uploaded.name) if uploaded else pasted
        if not text.strip():
            st.error("ارفع ملف أو الصق نص الأول.")
            st.stop()
        with st.spinner("جاري التحليل..."):
            result = summarize_email(text) if kind == "إيميل" else summarize_contract(text)
    except Exception as e:  # noqa: BLE001
        st.error(f"حصل خطأ: {e}")
        st.stop()

    st.subheader("الملخص")
    st.write(result.summary)

    if kind == "إيميل":
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}[result.priority]
        st.markdown(f"**الأولوية:** {icon} {result.priority} — {result.priority_reason}")
        st.markdown("**المطلوب منك:**")
        for a in result.action_items or ["لا يوجد"]:
            st.markdown(f"- {a}")
        st.markdown("**المواعيد:**")
        for d in result.deadlines or ["لا يوجد"]:
            st.markdown(f"- {d}")
    else:
        st.markdown(f"**الأطراف:** {'، '.join(result.parties)}")
        st.markdown(f"**المدة:** {result.term}")
        st.markdown(f"**الدفع:** {result.payment}")
        st.markdown(f"**الإنهاء:** {result.termination}")
        st.markdown("**الالتزامات:**")
        for c in result.obligations:
            st.markdown(f"- **{c.topic}** ({c.reference}): {c.detail}")
        st.markdown("**⚠️ بنود تحتاج انتباه:**")
        for c in result.risks:
            st.markdown(f"- **{c.topic}** ({c.reference}): {c.detail}")
        st.markdown("**❓ صياغات غامضة:**")
        for c in result.ambiguities or []:
            st.markdown(f"- **{c.topic}** ({c.reference}): {c.detail}")
        if not result.ambiguities:
            st.markdown("- لا يوجد")

    with st.expander("JSON الخام"):
        st.json(result.model_dump())
