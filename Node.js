const express = require('express');
const path = require('path');
const app = express();

// إعداد منفذ Render المباشر
const PORT = process.env.PORT || 3000;

// تقديم الملفات الثابتة
app.use(express.static(__dirname));

// التوجيه إلى الواجهة الرئيسية
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// بدء التشغيل
app.listen(PORT, () => {
    console.log(`========================================`);
    console.log(`🚀 OKX Scalper Server is live on port ${PORT}`);
    console.log(`========================================`);
});
