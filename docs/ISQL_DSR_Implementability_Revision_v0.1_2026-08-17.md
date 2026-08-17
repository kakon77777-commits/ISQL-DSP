# 可實作的無限光譜量化語言
## 有限活動光譜、動態語意狀態與多投影 Runtime 架構

**英文題名：** Implementable Infinite Spectral Quantization Language: Finite-Active Spectra, Dynamic Semantic State, and Multi-Projection Runtime Architecture  
**架構代號：** ISQL-DSR  
**版本：** v0.1  
**日期：** 2026-08-17  
**作者：** Neo.K  
**組織：** EveMissLab／一言諾科技有限公司  
**文件狀態：** 內部研究論文／可實作性修正版  

---

## 摘要

早期無限光譜量化語言相關構想，曾以「單符號高密度語意」、「無限維語意空間」、「拓撲奇異點」、「極限壓縮」與「完整語義宇宙」等強命題，試圖重新思考語言、記憶與機器表示的底層形式。這些構想具有研究啟發性，但其中若干敘述依賴無限精度、未定義的重構規則、未被證成的拓撲假設，或把理論極限與工程能力混為一談，因此不適合作為當代可執行系統的直接規格。

本文提出一個重新定錨的內部版本：**ISQL Dynamic Spectrum Runtime（ISQL-DSR）**。新版不否定舊構想的長期方向，而把核心要求改寫為「十年內可逐步實作、可測量、可回復、可版本化、可在有限資源上運行」。其中，「無限」不再表示單次計算必須處理真正的無限維向量或無限精度數值，而表示語意座標系統具有**開放式、無預設上限的擴展能力**；任一實際時間點只允許有限數量的活動維度。

本文將語意物件定義為具有穩定身份、語境、有限活動光譜、型別關係圖、多重投影與狀態歷史的動態結構。其核心形式為：

$$
\mathcal{S}_t=
(I,\Gamma_t,A_t,G_t,P_t,H_t),
\qquad |A_t|<\infty.
$$

其中 $I$ 是穩定身份，$\Gamma_t$ 是語境，$A_t$ 是有限活動光譜，$G_t$ 是型別關係圖，$P_t$ 是多投影集合，$H_t$ 是可重播歷史。語意不再被等同於單一整數 ID、單一 embedding 或單一符號；Registry ID 僅是穩定引用。Runtime 的任務不是宣稱「完整理解」語言，而是提供一個可讓不同模型、程式與人類工具共同操作的、可驗證的外部語意狀態層。

本文進一步提出：有限活動／無限可擴展原則、區間光譜、語境更新、關係優先、空間語意、多投影、分級 round-trip、語意差異、狀態轉移與十年實作路線。新版 ISQL-DSR 的定位不是取代 RDF、AMR、知識圖譜、向量符號架構或神經符號 AI，而是嘗試把這些既有方向中分散存在的「身份、結構、狀態、投影、版本與執行」問題，收斂為一個可運行的 AI-native semantic runtime。

**關鍵詞：** ISQL、動態語意、有限活動光譜、語意狀態、語意中介表示、多投影、神經符號 AI、Agent Runtime、語意 Registry

---

# 1. 問題重新定義

## 1.1 舊構想的價值與問題

早期版本提出數個強方向：

- 單符號可以代表極高密度甚至理論上無界的語意；
- 語意不是扁平字串，而是高維結構；
- 關係、位置、時間與上下文應進入表示本體；
- 表示應可分層展開，而不是一次性凍結；
- AI 應能在比自然語言更結構化的機器表示層交換資訊。

這些方向仍值得保留。但下列命題若沒有額外證明，不應再作為工程事實：

1. 一個有限物理符號可無條件承載任意無限資訊；
2. 任意自然語意都存在唯一且完整的有限拓撲不變量；
3. 任意高維語意都可以無損壓縮到固定低維表示；
4. 通用語意檢索可以在未計入索引與 Registry 成本時宣稱為 $O(1)$；
5. 一個固定維度向量可以保證固定比例的「語意保真度」；
6. 只要得到數字座標，就等於得到語意本身；
7. 由 AI 生成的語意結構可以在沒有外部驗證時視為真實世界的精確模型。

新版因此採用一個較嚴格的原則：

> **凡是核心 Runtime 所必需的機制，都必須存在有限表示、明確資料結構、可執行演算法、失敗模式與測試方法。無法做到者只能列為長期猜想，不得成為核心依賴。**

本文稱此為**當代可實作性原則**。

---

# 2. 「無限」的重新定義

## 2.1 從實際無限改為可擴展無界

新版不要求電腦在某一時刻保存或操作真正無限維物件。

定義一個概念上的語意軸宇宙：

$$
\mathbb{A}=\{a_1,a_2,a_3,\ldots\}.
$$

$\mathbb{A}$ 可以在系統演化中持續增加，不預先宣告固定最大維度。但在任一實際狀態 $t$，只有有限活動子集：

$$
A_t\subset\mathbb{A},
\qquad |A_t|=K_t<\infty.
$$

因此「無限光譜」在工程上改寫為：

$$
\boxed{
\text{unbounded extensibility}
+
\text{finite active computation}
}
$$

這使舊版的「無限維」直覺得以保留，但不再依賴不可能的實際無限計算。

## 2.2 解析度也是有限的

任一 axis 的數值、區間、機率或集合都必須具有實際序列化方式。Runtime 不允許「無限精度浮點數」作為必要欄位。

若某語意需要更高解析度，系統採用 refinement：

$$
A_t^{(r)}
\rightarrow
A_t^{(r+1)}.
$$

增加的是表示解析度，而不是假裝已經持有無限精度真值。

---

# 3. 動態語意物件

## 3.1 基本定義

ISQL-DSR 的核心物件定義為：

$$
\boxed{
\mathcal{S}_t=(I,\Gamma_t,A_t,G_t,P_t,H_t)
}
$$

其中：

- $I$：Identity，穩定身份；
- $\Gamma_t$：Context，當前語境；
- $A_t$：Active Spectrum，有限活動光譜；
- $G_t$：Typed Relation Graph，型別關係圖；
- $P_t$：Projection Set，多投影集合；
- $H_t$：History / Provenance，歷史與來源。

這個定義刻意把「物件身份」與「物件目前如何被理解」拆開。

因此：

$$
I(\mathcal{S}_t)=I(\mathcal{S}_{t+1})
$$

可以成立，同時：

$$
A_t\neq A_{t+1}
$$

或：

$$
G_t\neq G_{t+1}.
$$

也就是說，表示可以演化，而身份不必漂移。

## 3.2 語意不是 Registry ID

令 Registry 提供穩定引用：

$$
r:\text{semantic component}\rightarrow\mathbb{N}.
$$

則整數 $r(x)$ 只代表「Registry 中的第幾個穩定項目」，不代表完整語意本身。

新版明確規定：

$$
\boxed{
\text{Registry ID}\neq\text{Meaning}
}
$$

Registry 的功能是去重、版本治理、快速引用與傳輸，不是把語意本體縮成一個神秘整數。

---

# 4. 有限活動光譜

## 4.1 Axis 定義

每一個活動語意軸可表示為：

$$
a_i=(k_i,D_i,V_i,U_i,r_i).
$$

其中：

- $k_i$：axis key；
- $D_i$：合法值域；
- $V_i$：當前值；
- $U_i$：不確定性；
- $r_i$：解析度或證據層級。

第一階段至少允許三種 $V_i$：

### 點值

$$
V_i=x.
$$

### 區間值

$$
V_i=[l_i,u_i].
$$

### 離散候選集合

$$
V_i\in\{x_1,x_2,\ldots,x_m\}.
$$

機率分布、模糊集合與更一般的測度表示可以在後續版本加入，但不應成為 v0.1 的必要條件。

## 4.2 為什麼使用區間

自然語意經常不是單點。例如「高風險」、「偏正式」、「接近完成」、「可能屬於 A 或 B」都更適合用區間或候選集合表示。

因此新版不再強迫：

$$
\text{meaning}\rightarrow\text{one point}.
$$

而允許：

$$
\text{meaning}\rightarrow\text{bounded region}.
$$

這裡的「光譜」是一個工程術語，表示多軸、有範圍、有解析度的語意狀態；它不預設必須具有傅立葉頻率、物理波函數或量子態的數學性質。

---

# 5. 關係、位置與結構

## 5.1 關係不應只是文字欄位

ISQL-DSR 將關係建模為 typed edge：

$$
e=(u,\rho,v,m),
$$

其中 $u,v$ 是語意物件或局部節點，$\rho$ 是關係型別，$m$ 是 metadata。

整體形成：

$$
G_t=(V_t,E_t).
$$

這使 relation 可以被查詢、比較、版本化與執行，而不是只存在於自然語言描述中。

## 5.2 位置可以是語意

對 EML-U 類型的空間表示，位置不只是 renderer 屬性。

例如：

$$
A\otimes_{\mathrm{UR}}+
\neq
A\otimes_{\mathrm{LR}}+.
$$

在 DSR 中，這可以被表示為不同的 typed attachment relation：

$$
(A,\mathrm{upper\_right\_attachment},+)
$$

與：

$$
(A,\mathrm{lower\_right\_attachment},+).
$$

因此 EML-U 不需要成為 DSR 的唯一表面語言；它可以是 DSR 的一種視覺投影。

---

# 6. 語境與時間內建

## 6.1 語境不是解碼器外部參數

舊式編碼常將 context 視為呼叫 decoder 時才額外提供的參數。新版則把語境放入語意物件狀態：

$$
\Gamma_t=(c_1,c_2,\ldots,c_n).
$$

當語境變化時，語意狀態允許發生 transition：

$$
\mathcal{S}_{t+1}
=
T(\mathcal{S}_t,e_t,\Gamma_{t+1}).
$$

$e_t$ 是新事件、觀察或輸入。

## 6.2 Transition 必須可重播

如果 Runtime 宣稱某狀態由上一狀態轉移而來，核心層至少應能保存：

- transition type；
- input event；
- affected axes；
- affected relations；
- previous version；
- new version；
- timestamp / shared instant reference；
- provenance；
- validator result。

因此歷史不是附註，而是狀態的一部分：

$$
H_t=(\tau_1,\tau_2,\ldots,\tau_t).
$$

這使「持續計算」從哲學口號轉為可追蹤的 event-sourced state evolution。

---

# 7. 同一語意物件的多投影

## 7.1 Projection 原則

同一語意物件可以被投影到不同表示：

$$
\pi_j:\mathcal{S}\rightarrow R_j.
$$

例如：

$$
\begin{aligned}
\pi_{NL}(\mathcal{S}) &\rightarrow \text{Natural Language},\\
\pi_{G}(\mathcal{S}) &\rightarrow \text{Graph},\\
\pi_{EML}(\mathcal{S}) &\rightarrow \text{EML-U Glyph},\\
\pi_{IR}(\mathcal{S}) &\rightarrow \text{Semantic IR},\\
\pi_{W}(\mathcal{S}) &\rightarrow \text{ISQL Core Wire}.
\end{aligned}
$$

這些表示不必字節相同，也不必資訊量相同。

## 7.2 Round-trip 不應只分「成功／失敗」

新版提出四級 round-trip：

### L0：Byte Exact

$$
D(E(x))=x.
$$

### L1：Structural Exact

表面字串可不同，但 canonical structure 完全相同。

### L2：Semantic Constraint Preservation

核心 axes、relations、effects 與 invariants 被保留。

### L3：Task Equivalence

在指定任務集合 $\mathcal{T}$ 下：

$$
\forall q\in\mathcal{T},
\quad q(x)=q(x').
$$

這避免把「自然語言看起來差不多」誤當成 exact reconstruction。

---

# 8. 與既有技術的關係

## 8.1 RDF 與知識圖譜

RDF 1.2 延續以 graph、triple、dataset 與精確語義規則表示 Web 資訊的方向，並在 2026 年進入 Candidate Recommendation 實作驗證階段。ISQL-DSR 不應宣稱「發明了關係圖」；其差異目標在於把 typed relations 與有限活動光譜、語境狀態、投影與 transition history 放在同一 runtime object 中。

## 8.2 AMR 與 meaning representation

AMR 類方法已長期以 graph 結構抽離表面語法，2024 至 2025 年的工作仍持續研究其跨語言用途、邏輯操作與 richer symbolic meaning representations。ISQL-DSR 因此不把「語意圖」當作唯一新意，而把 graph 視為多投影之一。

## 8.3 Semantic IR

GraphQ IR 等研究已證明，中介表示可以統一不同 graph query language 的 semantic parsing。ULEI 類架構也可採相同思路：不同語言或視覺形式先進入 canonical semantic object，再投影到目標語言。

## 8.4 Vector Symbolic Architectures

VSA／Hyperdimensional Computing 以高維向量進行 binding、bundling 與結構表示，近年的研究仍在探索其語意分解與空間推理能力。ISQL-DSR 與 VSA 可以互補：某些 axis 或 relation group 可用向量表示，但 DSR 不要求整個語意物件只能存在於單一連續向量空間。

## 8.5 Neuro-symbolic AI

近期神經符號工作持續探索讓 LLM 與符號約束、graph reasoning、外部 solver 或 structured memory 協作。ISQL-DSR 的基本立場與此一致：

$$
\text{Model}
\rightarrow
\text{Structured Semantic Proposal}
\rightarrow
\text{Runtime Validation}
$$

而不是：

$$
\text{Model Output}=\text{Ground Truth}.
$$

---

# 9. 與現有 ISQL Core Runtime 的分工

現有可用版本應繼續保留，其價值主要在：

- stable content identity；
- addressing；
- registry；
- versioning；
- canonical serialization；
- exact recovery boundary；
- digits-only / compact wire；
- deterministic tests。

新版 DSR 不應重寫這些已經穩定的底層能力。

建議分層：

$$
\boxed{
\text{ISQL Core}
=
\text{Identity + Registry + Codec + Wire + Recovery}
}
$$

$$
\boxed{
\text{ISQL-DSR}
=
\text{Spectrum + Relation + Context + State + Projection + Evolution}
}
$$

兩者透過 bridge 銜接：

$$
\mathcal{S}_t
\xrightarrow{\text{canonicalize}}
\text{Core SEM/STATE Packet}
\xrightarrow{\text{encode}}
\text{Wire}.
$$

這種分工可以讓對外可用的 Core 保持簡潔，同時讓內部研究版本追求更強的語意與動態能力。

---

# 10. v0.1 最小可行規格

ISQL-DSR v0.1 不追求完整語言，不需要先支援任意 AI，也不需要先證明拓撲語意理論。

只要求以下六件事：

1. 語意物件具有穩定 identity；
2. 一個物件可含有限數量 typed axes；
3. axis 支援 point、interval、discrete candidates；
4. 物件可形成 typed relation graph；
5. context event 可產生可重播 state transition；
6. canonical form 可以 exact round-trip。

最低 canonical invariant：

$$
D(C(\mathcal{S}))=\mathcal{S}.
$$

其中 $C$ 是 canonical encoder，$D$ 是 canonical decoder。

AI adapter 只負責：

$$
\text{Natural Language}
\xrightarrow{\text{AI}}
\widehat{\mathcal{S}}.
$$

注意 $\widehat{\mathcal{S}}$ 是**提案**，不是未經驗證的真值。

---

# 11. 可驗證研究假說

新版把過去的強宣言改為可被否證的工程假說。

## H1：結構化語意穩定性

對同一來源輸入，不同模型生成的 DSR object 經 canonicalization 後，其核心 axis / relation agreement 高於純自然語言摘要的一致性。

## H2：狀態持久化效率

對長期 Agent 任務，保存 state transition 與 semantic diff 可以減少重新回放完整上下文所需的 token、時間或 I/O 成本。

## H3：多投影保真

對選定 domain，透過 canonical semantic object 進行：

$$
L_A\rightarrow\mathcal{S}\rightarrow L_B
$$

比直接：

$$
L_A\rightarrow L_B
$$

更容易測量與定位語意損失。

## H4：Registry 的攤銷效益

當相同 semantic atoms、relation types 與 schema 被大量重用時，Registry reference 可以降低重複序列化成本；但必須把 Registry 本身的建立、同步與版本成本計入總成本。

## H5：有限光譜優於固定單點表示的特定任務

在需要不確定性、範圍語意、版本演化或多候選解釋的 domain，interval / candidate spectrum 應比單一 label 或單一 scalar 更能保留可操作資訊。

這些都必須以實驗驗證，而不是以名稱或數學符號本身視為成立。

---

# 12. 評估矩陣

任何未來版本至少應報告：

- canonical round-trip pass rate；
- schema validation pass rate；
- transition replay pass rate；
- cross-version decode success rate；
- cross-model structural agreement；
- semantic constraint preservation；
- unresolved ambiguity rate；
- uncertainty calibration；
- encoded size；
- Registry size；
- amortized total storage；
- encoding / decoding latency；
- semantic diff precision；
- projection failure rate；
- exact / structural / semantic / task-level round-trip 分級結果。

不得只報告「壓縮後字串比較短」；也不得在忽略 Registry、模型推理與外部索引成本時宣稱系統整體壓縮率。

---

# 13. 十年內實作路線

以下是研究路線，不是時間保證。

## Phase I：0–2 年

目標：建立 deterministic semantic runtime。

- DSR object schema；
- finite-active axes；
- typed relation graph；
- context event；
- transition log；
- canonical serialization；
- Core bridge；
- EML-U projection；
- natural-language projection；
- test corpus；
- round-trip validator。

## Phase II：2–5 年

目標：建立共享狀態與跨模型操作。

- multi-model semantic adapters；
- semantic diff / merge；
- conflict object；
- uncertainty-aware fusion；
- shared Registry governance；
- domain-specific schema；
- Agent state persistence；
- Semantic IR / EXEC bridge；
- cross-language projection。

## Phase III：5–10 年

目標：研究更高階的自適應語意空間。

- automatic axis proposal；
- ontology evolution；
- relation-type induction；
- topology-inspired structure analysis；
- domain-specific spectral geometry；
- distributed Registry；
- standardized inter-agent semantic transport；
- compiled semantic execution where semantics are sufficiently formalized。

只有在這些有限系統累積足夠實驗證據後，才值得重新檢驗「更強的無限維、拓撲不變量或極限壓縮」命題。

---

# 14. 保留但降級為遠期猜想的舊命題

以下概念不刪除，但不再作為當前 Runtime 的已成立事實：

### C1：單符號極限表示

是否存在某類高度共享先驗下，使極短 reference 可間接恢復極大語意結構。

### C2：語意拓撲不變量

是否存在特定 domain 的語意結構，可以由可計算拓撲量穩定描述。

### C3：自適應無界座標宇宙

是否能在長期運行中自動產生、合併與淘汰 semantic axes，而不使版本治理失控。

### C4：高階語意編譯

是否能將部分自然語意編譯成具有可驗證 effect、state transition 與 execution semantics 的 machine-native object。

### C5：極限壓縮

是否存在依賴大規模共享世界模型、Registry 或生成規則的語意 reference system，使新增資料的邊際表示成本顯著下降。

這些都是研究問題，不是現在的產品規格。

---

# 15. 結論

新版 ISQL 的核心轉變，可以濃縮為一句話：

> **不再要求當代電腦實作「真正的無限」，而是建立一個任何時刻都有限、但可以持續擴展、細化、連接、投影與演化的語意計算空間。**

因此，早期理論中最重要的部分沒有被放棄：語意仍被視為高維、關係化、可展開、語境依賴且具有動態歷史的對象。但「單符號宇宙」、「無限精度」、「固定低維完整重構」、「普遍 $O(1)$ 語意檢索」等過強命題被移出核心工程層。

新的架構目標不是證明所有語意都能被完美數學化，而是先回答一個更可操作的問題：

$$
\boxed{
\text{能否建立一個跨模型、跨表示、可版本化、可回復、可執行驗證的共享語意狀態層？}
}
$$

如果答案逐步為是，那麼 ISQL-DSR 將不是「把文字轉成數字」的壓縮器，而會成為一個介於模型與應用之間的外部認知／語意 Runtime。更強的舊命題則應等待這個有限系統累積足夠證據後，再被重新提出、修正或否證。

---

# 參考文獻

1. W3C RDF & SPARQL Working Group. *RDF 1.2 Concepts and Abstract Data Model*. Candidate Recommendation Snapshot, 2026-04-07. https://www.w3.org/TR/rdf12-concepts/
2. W3C RDF & SPARQL Working Group. *RDF 1.2 Semantics*. Candidate Recommendation Snapshot, 2026-04-07. https://www.w3.org/TR/rdf12-semantics/
3. Wein, S., & Schneider, N. *Assessing the Cross-linguistic Utility of Abstract Meaning Representation*. Computational Linguistics, 2024. https://aclanthology.org/2024.cl-2.1/
4. Bao, Y. et al. *Abstract Meaning Representation-Based Logic-Driven Data Augmentation for Logical Reasoning*. Findings of ACL, 2024. https://aclanthology.org/2024.findings-acl.353/
5. Nie, F. et al. *GraphQ IR: Unifying the Semantic Parsing of Graph Query Languages with One Intermediate Representation*. EMNLP, 2022. https://aclanthology.org/2022.emnlp-main.394/
6. Zhang, L. et al. *Neural Semantic Parsing with Extremely Rich Symbolic Meaning Representations*. Computational Linguistics, 2025. https://aclanthology.org/2025.cl-1.7/
7. Yeung, C., Poduval, P., & Imani, M. *Self-Attention Based Semantic Decomposition in Vector Symbolic Architectures*. arXiv:2403.13218, 2024. https://arxiv.org/abs/2403.13218
8. Penzkofer, A., Shi, L., & Bulling, A. *VSA4VQA: Scaling a Vector Symbolic Architecture to Visual Question Answering on Natural Images*. arXiv:2405.03852, 2024. https://arxiv.org/abs/2405.03852
9. *Logically Consistent Language Models via Neuro-Symbolic Integration*. ICLR 2025. https://openreview.net/forum?id=7PGluppo4k
10. *NeSyPr: Neurosymbolic Proceduralization For Efficient Embodied Reasoning*. NeurIPS 2025. https://openreview.net/forum?id=a8sJEH4Cjb

---

# 版本註記

本文件是「可實作性修正版」的第一篇基礎論文。其主要任務是重新定義工程邊界，不宣稱已證明通用語意拓撲、無限壓縮或跨模型完整語意等價。後續文件應分別處理：

- ISQL-DSR v0.1 formal schema；
- Spectrum Axis Specification；
- Typed Relation & Spatial Attachment Specification；
- State Transition / Replay Protocol；
- Multi-Projection & Round-Trip Semantics；
- ISQL Core Bridge；
- Experimental Benchmark Protocol。
