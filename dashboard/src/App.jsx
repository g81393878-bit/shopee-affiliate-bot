import React, { useState, useEffect } from 'react';

function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [toastMessage, setToastMessage] = useState('');

  // AI Affiliate Data States
  const [affiliateProducts, setAffiliateProducts] = useState([]);
  const [selectedAffiliateProductId, setSelectedAffiliateProductId] = useState(null);
  const [affiliateSummary, setAffiliateSummary] = useState({
    total_views: 0,
    total_clicks: 0,
    total_orders: 0,
    total_commission: 0,
    average_ctr: 0.0,
    conversion_rate: 0.0,
    earnings_per_click: 0.0
  });
  const [selectedAnalysis, setSelectedAnalysis] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [selectedStyle, setSelectedStyle] = useState('standard');
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);
  const [showAddProductModal, setShowAddProductModal] = useState(false);
  
  const [newProductForm, setNewProductForm] = useState({
    name: '',
    category: '',
    price: '',
    rating: '',
    sales_count: '',
    commission: '',
    affiliate_url: ''
  });
  
  const [perfLogForm, setPerfLogForm] = useState({
    views: '',
    clicks: '',
    orders: '',
    commission_earned: '',
    date: new Date().toISOString().split('T')[0]
  });

  const BACKEND_URL = "http://localhost:8000/api";

  const showToast = (message) => {
    setToastMessage(message);
    setTimeout(() => {
      setToastMessage('');
    }, 3000);
  };

  // --- AI Affiliate API Connection Methods ---
  const fetchAffiliateProducts = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/products/`);
      if (res.ok) {
        const data = await res.json();
        setAffiliateProducts(data);
        if (data.length > 0 && !selectedAffiliateProductId) {
          setSelectedAffiliateProductId(data[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch affiliate products", err);
    }
  };

  const fetchAffiliateSummary = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/performance/summary`);
      if (res.ok) {
        const data = await res.json();
        setAffiliateSummary(data);
      }
    } catch (err) {
      console.error("Failed to fetch affiliate summary", err);
    }
  };

  useEffect(() => {
    fetchAffiliateProducts();
    fetchAffiliateSummary();
  }, []);

  useEffect(() => {
    if (selectedAffiliateProductId) {
      const fetchAnalysis = async () => {
        try {
          setIsAnalyzing(true);
          const res = await fetch(`${BACKEND_URL}/products/${selectedAffiliateProductId}/analyze`, {
            method: 'POST'
          });
          if (res.ok) {
            const data = await res.json();
            setSelectedAnalysis(data);
          }
          setIsAnalyzing(false);
        } catch (err) {
          console.error("Failed to analyze product", err);
          setIsAnalyzing(false);
        }
      };
      fetchAnalysis();
    } else {
      setSelectedAnalysis(null);
    }
  }, [selectedAffiliateProductId]);

  const handleAddProduct = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        name: newProductForm.name,
        category: newProductForm.category || "General",
        price: parseFloat(newProductForm.price) || 0.0,
        rating: parseFloat(newProductForm.rating) || 0.0,
        sales_count: parseInt(newProductForm.sales_count) || 0,
        commission: parseFloat(newProductForm.commission) || 0.0,
        affiliate_url: newProductForm.affiliate_url
      };
      
      const res = await fetch(`${BACKEND_URL}/products/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        showToast("เพิ่มสินค้าและคำนวณ Heuristic Score สำเร็จ!");
        setShowAddProductModal(false);
        setNewProductForm({
          name: '',
          category: '',
          price: '',
          rating: '',
          sales_count: '',
          commission: '',
          affiliate_url: ''
        });
        fetchAffiliateProducts();
      } else {
        showToast("เกิดข้อผิดพลาดในการเพิ่มสินค้า");
      }
    } catch (err) {
      console.error(err);
      showToast("เชื่อมต่อเซิร์ฟเวอร์หลังบ้านล้มเหลว");
    }
  };

  const handleAnalyzeProduct = async () => {
    if (!selectedAffiliateProductId) return;
    try {
      setIsAnalyzing(true);
      const res = await fetch(`${BACKEND_URL}/products/${selectedAffiliateProductId}/analyze`, {
        method: 'POST'
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedAnalysis(data);
        showToast("AI วิเคราะห์สินค้าเรียบร้อย!");
        fetchAffiliateProducts();
      } else {
        showToast("วิเคราะห์ล้มเหลว");
      }
      setIsAnalyzing(false);
    } catch (err) {
      console.error(err);
      showToast("ล้มเหลวในการเชื่อมต่อกับ AI");
      setIsAnalyzing(false);
    }
  };

  const handleRegenerateScript = async () => {
    if (!selectedAffiliateProductId) return;
    try {
      setIsGeneratingScript(true);
      const res = await fetch(`${BACKEND_URL}/products/${selectedAffiliateProductId}/script?style=${selectedStyle}`, {
        method: 'POST'
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedAnalysis(prev => ({
          ...prev,
          script: data
        }));
        showToast(`เจนสคริปต์สไตล์ ${selectedStyle} สำเร็จ!`);
      } else {
        showToast("สคริปต์ล้มเหลว");
      }
      setIsGeneratingScript(false);
    } catch (err) {
      console.error(err);
      showToast("ล้มเหลวในการสื่อสารกับ AI");
      setIsGeneratingScript(false);
    }
  };

  const handleLogPerformanceSubmit = async (e) => {
    e.preventDefault();
    if (!selectedAffiliateProductId || !selectedAnalysis?.content_id) {
      showToast("กรุณาสั่งให้ AI วิเคราะห์เขียนบทวิดีโอ (Analyze) ก่อนบันทึกสถิติครับ");
      return;
    }
    try {
      const payload = {
        content_id: selectedAnalysis.content_id,
        date: perfLogForm.date,
        views: parseInt(perfLogForm.views) || 0,
        clicks: parseInt(perfLogForm.clicks) || 0,
        orders: parseInt(perfLogForm.orders) || 0,
        commission_earned: parseFloat(perfLogForm.commission_earned) || 0.0
      };
      
      const res = await fetch(`${BACKEND_URL}/performance/contents/${selectedAnalysis.content_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        showToast("บันทึกสถิติยอดการโพสต์เรียบร้อย!");
        setPerfLogForm({
          views: '',
          clicks: '',
          orders: '',
          commission_earned: '',
          date: new Date().toISOString().split('T')[0]
        });
        fetchAffiliateSummary();
      } else {
        showToast("บันทึกยอดคลิปวิดีโอล้มเหลว");
      }
    } catch (err) {
      console.error(err);
      showToast("เชื่อมต่อฐานข้อมูลหลังบ้านไม่สำเร็จ");
    }
  };

  return (
    <div className="h-screen bg-transparent text-slate-100 font-sans flex flex-col overflow-hidden relative">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-[9999] animate-bounce">
          <div className="bg-indigo-600 text-white px-6 py-3 rounded-xl shadow-xl font-medium flex items-center gap-2 border border-indigo-500">
            <span>✨</span> {toastMessage}
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden h-full">
        {/* Sidebar - Product List */}
        <div className="w-72 bg-slate-900/40 backdrop-blur-2xl border-r border-slate-700/50 flex flex-col h-full shadow-[4px_0_24px_rgba(0,0,0,0.2)] z-10">
          <div className="p-5 border-b border-slate-700/50 bg-slate-900/40 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <span className="text-white font-bold text-lg">AI</span>
            </div>
            <div>
              <div className="font-bold text-lg bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400">
                Affiliate AI
              </div>
              <div className="text-xs text-slate-400">
                Product Intelligence
              </div>
            </div>
          </div>

          <div className="p-4 flex-1 overflow-y-auto">
            {/* Add Product Button */}
            <div className="mb-4">
              <button 
                onClick={() => setShowAddProductModal(true)}
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2.5 px-4 rounded-xl text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-indigo-500/20"
              >
                ➕ เพิ่มสินค้า Shopee
              </button>
            </div>

            {/* Search Bar */}
            <div className="mb-4">
              <input 
                type="text" 
                placeholder="ค้นหาสินค้า..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex justify-between items-center mb-4 px-1">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">อันดับความน่าทำคลิป ({affiliateProducts.length})</h3>
            </div>

            <div className="space-y-3">
              {affiliateProducts
                .filter(p => p.name.toLowerCase().includes(searchQuery.toLowerCase()))
                .map(product => (
                  <button
                    key={product.id}
                    onClick={() => setSelectedAffiliateProductId(product.id)}
                    className={`w-full text-left px-4 py-3 rounded-2xl transition-all flex items-center gap-3 relative overflow-hidden ${
                      selectedAffiliateProductId === product.id 
                        ? 'bg-indigo-500/20 border border-indigo-500/50 shadow-[0_0_15px_rgba(99,102,241,0.15)]' 
                        : 'bg-slate-900/30 border border-transparent hover:bg-slate-800/50'
                    }`}
                  >
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                      product.score >= 80 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' :
                      product.score >= 50 ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/30' : 
                      'bg-slate-800 text-slate-400 border border-slate-700'
                    }`}>
                      {product.score}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold truncate text-slate-100">
                        {product.name}
                      </div>
                      <div className="text-[11px] text-slate-500 truncate mt-0.5">
                        ฿{product.price} • คอม ฿{product.commission}
                      </div>
                    </div>
                    {selectedAffiliateProductId === product.id && (
                      <div className="absolute right-0 top-0 bottom-0 w-1 bg-indigo-500 rounded-l-full"></div>
                    )}
                  </button>
                ))}
              {affiliateProducts.length === 0 && (
                <div className="text-sm text-slate-500 text-center py-8 bg-slate-900/30 rounded-xl border border-slate-800 border-dashed">
                  ไม่มีสินค้าในระบบ
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto h-full bg-transparent relative">
          <div className="p-8 max-w-7xl mx-auto space-y-6">
            
            {/* Header / Top Stats Grid */}
            <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-[2.5rem] p-6 shadow-2xl">
              <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-200 to-purple-200 mb-6">
                📊 สถิติผลงาน Affiliate ภาพรวมของระบบ
              </h1>
              
              <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-4">
                <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-xs text-slate-400 font-semibold">👀 ยอดผู้ชม</span>
                  <span className="text-xl font-bold text-slate-200 mt-2">{Number(affiliateSummary.total_views).toLocaleString()}</span>
                </div>
                <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-xs text-slate-400 font-semibold">🖱️ ยอดคลิก</span>
                  <span className="text-xl font-bold text-indigo-400 mt-2">{Number(affiliateSummary.total_clicks).toLocaleString()}</span>
                </div>
                <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-xs text-slate-400 font-semibold">📦 ยอดสั่งซื้อ</span>
                  <span className="text-xl font-bold text-indigo-400 mt-2">{Number(affiliateSummary.total_orders).toLocaleString()}</span>
                </div>
                <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-xs text-slate-400 font-semibold">💰 ค่าคอมรวม</span>
                  <span className="text-xl font-bold text-emerald-400 mt-2">฿{Number(affiliateSummary.total_commission).toLocaleString()}</span>
                </div>
                <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-xs text-slate-400 font-semibold">📊 CTR</span>
                  <span className="text-xl font-bold text-indigo-400 mt-2">{affiliateSummary.average_ctr}%</span>
                </div>
                <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-xs text-slate-400 font-semibold">📈 Conversion</span>
                  <span className="text-xl font-bold text-indigo-400 mt-2">{affiliateSummary.conversion_rate}%</span>
                </div>
                <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-xs text-slate-400 font-semibold">💵 EPC</span>
                  <span className="text-xl font-bold text-indigo-400 mt-2">฿{affiliateSummary.earnings_per_click}</span>
                </div>
              </div>
            </div>

            {!selectedAffiliateProductId ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                <div className="text-6xl mb-4 opacity-20">💸</div>
                <div className="text-lg">เลือกสินค้าด้านซ้ายเพื่อดูคะแนน สคริปต์วิดีโอ และการบันทึกยอดขาย</div>
              </div>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                {/* Product Info & Log Performance */}
                <div className="space-y-6">
                  {/* Product Details Card */}
                  {(() => {
                    const prod = affiliateProducts.find(p => p.id === selectedAffiliateProductId);
                    if (!prod) return null;
                    return (
                      <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-[2rem] p-6 shadow-2xl relative overflow-hidden">
                        <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/10 rounded-bl-[4rem] flex items-center justify-center border-l border-b border-indigo-500/20">
                          <span className="text-3xl font-extrabold text-indigo-400">{prod.score}</span>
                        </div>
                        <h2 className="text-lg font-bold text-white pr-20">{prod.name}</h2>
                        <span className="inline-block bg-slate-800 text-slate-400 text-xs px-2.5 py-1 rounded-full font-medium mt-2">{prod.category}</span>
                        
                        <div className="grid grid-cols-2 gap-4 mt-6 pt-6 border-t border-slate-800">
                          <div>
                            <span className="text-[11px] text-slate-500 block">💵 ราคาสินค้า</span>
                            <span className="text-base font-bold text-slate-200">฿{prod.price}</span>
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 block">📈 คอมมิชชัน/ชิ้น</span>
                            <span className="text-base font-bold text-emerald-400">฿{prod.commission}</span>
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 block">⭐️ คะแนนรีวิว</span>
                            <span className="text-sm font-bold text-slate-200">⭐ {prod.rating} / 5.0</span>
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 block">🛍️ ยอดขายแล้ว</span>
                            <span className="text-sm font-bold text-slate-200">{prod.sales_count} ชิ้น</span>
                          </div>
                        </div>

                        <div className="mt-6 pt-6 border-t border-slate-800">
                          <a 
                            href={prod.affiliate_url || '#'} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200 py-3 px-4 rounded-xl text-xs font-bold transition-colors flex items-center justify-center gap-2 border border-slate-700"
                          >
                            🔗 ไปยังลิงก์ Shopee Affiliate
                          </a>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Log Performance Card */}
                  <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-[2rem] p-6 shadow-2xl">
                    <h3 className="text-base font-bold text-white mb-4">📈 บันทึกสถิติยอด Views / Clicks ของคลิปวิดีโอ</h3>
                    <form onSubmit={handleLogPerformanceSubmit} className="space-y-4">
                      <div>
                        <label className="text-xs text-slate-400 block mb-1">วันที่โพสต์ / บันทึกผล</label>
                        <input 
                          type="date"
                          value={perfLogForm.date}
                          onChange={(e) => setPerfLogForm({...perfLogForm, date: e.target.value})}
                          className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                          required
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">ยอดผู้ดู (Views)</label>
                          <input 
                            type="number"
                            placeholder="0"
                            value={perfLogForm.views}
                            onChange={(e) => setPerfLogForm({...perfLogForm, views: e.target.value})}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">ยอดคลิก (Clicks)</label>
                          <input 
                            type="number"
                            placeholder="0"
                            value={perfLogForm.clicks}
                            onChange={(e) => setPerfLogForm({...perfLogForm, clicks: e.target.value})}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                            required
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">จำนวนออเดอร์ (Orders)</label>
                          <input 
                            type="number"
                            placeholder="0"
                            value={perfLogForm.orders}
                            onChange={(e) => setPerfLogForm({...perfLogForm, orders: e.target.value})}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                            required
                          />
                        </div>
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">ยอดคอมมิชชันที่ได้ (บาท)</label>
                          <input 
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            value={perfLogForm.commission_earned}
                            onChange={(e) => setPerfLogForm({...perfLogForm, commission_earned: e.target.value})}
                            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                            required
                          />
                        </div>
                      </div>
                      <button 
                        type="submit"
                        className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 px-4 rounded-xl text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20"
                      >
                        💾 บันทึกสถิติยอด
                      </button>
                    </form>
                  </div>
                </div>

                {/* AI Script & AIDA Analysis Column */}
                <div className="xl:col-span-2 space-y-6">
                  {/* AI Evaluation */}
                  <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-700/50 rounded-[2rem] p-6 shadow-2xl relative overflow-hidden">
                    <div className="flex justify-between items-center mb-6">
                      <h3 className="text-base font-bold text-white flex items-center gap-2">
                        <span>🤖</span> บทวิเคราะห์โอกาสขายและการสร้างสคริปต์โฆษณาด้วย AI
                      </h3>
                      <button 
                        onClick={handleAnalyzeProduct}
                        disabled={isAnalyzing}
                        className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 text-white font-bold py-2 px-4 rounded-xl text-xs transition-colors shadow-lg shadow-indigo-500/20"
                      >
                        {isAnalyzing ? "กำลังวิเคราะห์..." : "🔄 รันระบบประเมิน AI ใหม่"}
                      </button>
                    </div>

                    {isAnalyzing && !selectedAnalysis ? (
                      <div className="flex flex-col items-center justify-center py-20 text-indigo-400">
                        <div className="animate-spin text-4xl mb-4">🔄</div>
                        <div>ระบบ AI กำลังประเมินสินค้าและสรุปสคริปต์ AIDA...</div>
                      </div>
                    ) : selectedAnalysis ? (
                      <div className="space-y-6">
                        {/* Rating Metrics & Score explanation */}
                        <div className="grid grid-cols-2 gap-4">
                          <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4">
                            <span className="text-[11px] text-slate-400 block font-semibold">คะแนน AI Score</span>
                            <div className="text-xl font-bold text-indigo-400 mt-1">{selectedAnalysis.ai_score} / 100</div>
                            <span className="text-[10px] text-slate-500 block mt-1">{selectedAnalysis.reasoning?.substring(0, 100)}...</span>
                          </div>
                          <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4">
                            <span className="text-[11px] text-slate-400 block font-semibold">คำแนะนำการทำช่อง</span>
                            <div className="text-xl font-bold text-emerald-400 mt-1">{selectedAnalysis.recommendation || "ควรทำคอนเทนต์"}</div>
                            <span className="text-[10px] text-slate-500 block mt-1">โอกาสการขายจากยอดความนิยมในปัจจุบัน</span>
                          </div>
                        </div>

                        {/* Analysis Reasoning Block */}
                        <div className="bg-slate-800/20 border border-slate-800 rounded-xl p-4">
                          <h4 className="text-xs font-bold text-slate-300 mb-2">💡 เหตุผลการประเมินวิเคราะห์:</h4>
                          <p className="text-xs text-slate-400 leading-relaxed">{selectedAnalysis.reasoning}</p>
                        </div>

                        {/* Script Style Generator Form */}
                        <div className="border-t border-slate-800 pt-6">
                          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
                            <h4 className="text-sm font-bold text-indigo-300">🎬 สคริปต์สั้น AIDA (สำหรับถ่ายคลิป)</h4>
                            <div className="flex gap-2 w-full sm:w-auto">
                              <select 
                                value={selectedStyle}
                                onChange={(e) => setSelectedStyle(e.target.value)}
                                className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                              >
                                <option value="standard">Standard (สไตล์ AIDA)</option>
                                <option value="tiktok">TikTok (เน้นกระแส สั้นกระชับ)</option>
                                <option value="review">Review (รีวิวป้ายยาตรงๆ)</option>
                                <option value="storytelling">Storytelling (แนวเล่าเรื่อง)</option>
                              </select>
                              <button 
                                onClick={handleRegenerateScript}
                                disabled={isGeneratingScript}
                                className="bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/30 text-indigo-300 font-bold py-1.5 px-3 rounded-lg text-xs transition-colors shrink-0"
                              >
                                {isGeneratingScript ? "กำลังเจน..." : "🪄 เจนใหม่"}
                              </button>
                            </div>
                          </div>

                          {/* Render Script blocks */}
                          <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6 space-y-4">
                            <div>
                              <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">🪝 Hook (ประโยคเปิดตัวดึงสายตา 3 วินาทีแรก)</span>
                              <p className="text-sm text-slate-200 mt-1 font-medium italic">"{selectedAnalysis.script?.hook}"</p>
                            </div>
                            
                            <div className="border-t border-slate-800 pt-3">
                              <span className="text-[10px] uppercase font-bold text-yellow-400 tracking-wider">🔥 Problem (ชี้ขยี้ปัญหาขัดใจที่คนเจอบ่อย)</span>
                              <p className="text-sm text-slate-300 mt-1">"{selectedAnalysis.script?.problem}"</p>
                            </div>
                            
                            <div className="border-t border-slate-800 pt-3">
                              <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">🛠️ Solution (เฉลยคุณสมบัติสุดเทพของสินค้าตัวนี้)</span>
                              <p className="text-sm text-slate-300 mt-1">"{selectedAnalysis.script?.solution}"</p>
                            </div>
                            
                            <div className="border-t border-slate-800 pt-3">
                              <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">🎯 CTA (Call to Action ปิดยอดสั่งซื้อ)</span>
                              <p className="text-sm text-slate-300 mt-1">"{selectedAnalysis.script?.cta}"</p>
                            </div>

                            <div className="border-t border-slate-800 pt-4 bg-slate-900/40 p-4 rounded-xl">
                              <span className="text-[10px] uppercase font-bold text-purple-400 tracking-wider">✍️ Caption / Hashtags สำหรับนำไปโพสต์</span>
                              <p className="text-xs text-slate-400 mt-1 leading-relaxed whitespace-pre-wrap">{selectedAnalysis.script?.caption}</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                        <div className="text-6xl mb-4 opacity-20">🤖</div>
                        <div className="text-sm">สินค้าตัวนี้ยังไม่ได้ถูกประเมินจากระบบ AI หรืออยู่ระหว่างดึงข้อมูล</div>
                        <button 
                          onClick={handleAnalyzeProduct}
                          disabled={isAnalyzing}
                          className="mt-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-2 px-6 rounded-xl text-xs transition-colors"
                        >
                          {isAnalyzing ? "กำลังประเมิน..." : "🚀 สั่งให้ AI ประเมินและสร้างสคริปต์"}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Add Product Modal */}
      {showAddProductModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-[fadeIn_0.2s_ease-out]">
          <div className="bg-slate-900 border border-slate-800 rounded-[2.5rem] w-full max-w-lg p-8 shadow-2xl relative">
            <h3 className="text-xl font-bold text-white mb-6">➕ เพิ่มข้อมูลสินค้า Shopee เพื่อเข้าสู่ระบบ</h3>
            
            <form onSubmit={handleAddProduct} className="space-y-4">
              <div>
                <label className="text-xs text-slate-400 block mb-1">ชื่อสินค้า (Product Name)</label>
                <input 
                  type="text"
                  placeholder="เช่น Xiaomi Smart Vacuum Cleaner"
                  value={newProductForm.name}
                  onChange={(e) => setNewProductForm({...newProductForm, name: e.target.value})}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 block mb-1">หมวดหมู่สินค้า (Category)</label>
                  <input 
                    type="text"
                    placeholder="เช่น เครื่องใช้ไฟฟ้า"
                    value={newProductForm.category}
                    onChange={(e) => setNewProductForm({...newProductForm, category: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">ราคาสินค้า (บาท)</label>
                  <input 
                    type="number"
                    step="0.01"
                    placeholder="1290.00"
                    value={newProductForm.price}
                    onChange={(e) => setNewProductForm({...newProductForm, price: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-slate-400 block mb-1">เรตติ้ง (Rating)</label>
                  <input 
                    type="number"
                    step="0.1"
                    max="5"
                    placeholder="4.8"
                    value={newProductForm.rating}
                    onChange={(e) => setNewProductForm({...newProductForm, rating: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">ยอดขายสะสม (ชิ้น)</label>
                  <input 
                    type="number"
                    placeholder="2500"
                    value={newProductForm.sales_count}
                    onChange={(e) => setNewProductForm({...newProductForm, sales_count: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">คอมมิชชัน (บาท)</label>
                  <input 
                    type="number"
                    step="0.01"
                    placeholder="99.00"
                    value={newProductForm.commission}
                    onChange={(e) => setNewProductForm({...newProductForm, commission: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-400 block mb-1">ลิงก์นายหน้า (Affiliate URL)</label>
                <input 
                  type="url"
                  placeholder="https://shope.ee/..."
                  value={newProductForm.affiliate_url}
                  onChange={(e) => setNewProductForm({...newProductForm, affiliate_url: e.target.value})}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex gap-4 pt-4">
                <button 
                  type="button"
                  onClick={() => setShowAddProductModal(false)}
                  className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold py-3 px-4 rounded-xl text-xs transition-colors"
                >
                  ยกเลิก
                </button>
                <button 
                  type="submit"
                  className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 px-4 rounded-xl text-xs transition-colors shadow-lg shadow-indigo-500/20"
                >
                  🚀 บันทึกสินค้า
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
