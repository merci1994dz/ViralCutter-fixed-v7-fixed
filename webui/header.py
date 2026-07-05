import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKING_DIR = os.path.dirname(CURRENT_DIR)
sys.path.append(WORKING_DIR)

from i18n.i18n import I18nAuto

i18n = I18nAuto("ar_SA")

badges = ""

description = """
<div style="text-align:center; direction: rtl; line-height: 1.8;">
  <h1 style="margin-bottom: 8px;">ViralCutter</h1>
  <p style="font-size: 1.05em; margin-bottom: 18px; color: #cbd5e1;">
    أداة عربية لتحويل الفيديوهات الطويلة إلى مقاطع قصيرة بشكل أوضح وأبسط، مع سجل تشغيل، وتقدم دقيق، وتقارير أخطاء مفهومة، وواجهة أنظف.
  </p>
  <div style="display:inline-block; text-align:right; background:rgba(255,255,255,0.05); padding:18px 22px; border-radius:14px; margin-bottom:18px; max-width:900px;">
    <p style="margin-bottom:10px;"><strong>ماذا تستطيع أن تفعل هنا؟</strong></p>
    <ul style="margin:0; padding-right:20px; line-height:1.9;">
      <li>✂️ <strong>قص احترافي</strong>: استخراج المقاطع المهمة مع ضبط أفضل للوجه والتوقيت.</li>
      <li>📝 <strong>ترجمة وضبط شكلها</strong>: التحكم بخطوط الترجمة وموقعها ومعاينتها قبل الحفظ.</li>
      <li>🤖 <strong>دعم الذكاء الاصطناعي</strong>: Gemini وG4F والنماذج المحلية من نفس الواجهة.</li>
      <li>📱 <strong>مناسب للفيديو العمودي</strong>: تحسينات خاصة بـ Shorts وReels وTikTok.</li>
    </ul>
  </div>
  <p style="color:#94a3b8; margin:0;">واجهة عربية كاملة، مرتبة، ومصممة لتبقى واضحة أثناء المهام الطويلة.</p>
</div>
"""