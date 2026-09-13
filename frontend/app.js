/* ---------------- State ---------------- */
let language = 'en';
let messages = [];              // Anthropic message history, mirrored from backend responses
let lastWeatherData = null;     // last weather bundle rendered (for language-switch refresh)
let lastResolved = null;        // {location, state, district} of the last successfully resolved place

const strings = {
  en: { placeholder: "Ask about weather, forecasts, or climate…", send: "Ask", idle: "idle", thinking: "thinking", live: "live · Open-Meteo" },
  hi: { placeholder: "मौसम, पूर्वानुमान या जलवायु के बारे में पूछें…", send: "पूछें", idle: "निष्क्रिय", thinking: "सोच रहा है", live: "लाइव · Open-Meteo" },
  bn: { placeholder: "আবহাওয়া, পূর্বাভাস বা জলবায়ু নিয়ে জিজ্ঞাসা করুন…", send: "জিজ্ঞাসা", idle: "নিষ্ক্রিয়", thinking: "ভাবছে", live: "লাইভ · Open-Meteo" }
};

/* ---------------- Weather icon (visual only, client-side) ---------------- */
function weatherIcon(code, size=22){
  const s = size;
  const stroke = 'stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"';
  if(code===0) return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:#E8A33D"><circle cx="12" cy="12" r="4.5" ${stroke}/><path d="M12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" ${stroke}/></svg>`;
  if([1,2,3].includes(code)) return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:#9AA3BC"><path d="M7 16a4 4 0 1 1 1-7.9A5 5 0 0 1 18 10a3.5 3.5 0 0 1-.5 7H7z" ${stroke}/></svg>`;
  if([45,48].includes(code)) return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:#9AA3BC"><path d="M3 10h14M3 14h18M6 18h12" ${stroke}/></svg>`;
  if([51,53,55,56,57,61,63,65,66,67,80,81,82].includes(code)) return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:#4FB6C7"><path d="M7 13a4 4 0 1 1 1-7.9A5 5 0 0 1 18 7a3.5 3.5 0 0 1-.5 7H7z" ${stroke}/><path d="M8 18l-1 2M12 18l-1 2M16 18l-1 2" ${stroke}/></svg>`;
  if([71,73,75,77,85,86].includes(code)) return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:#EDEEF2"><path d="M12 2v20M4.5 6.5l15 11M19.5 6.5l-15 11" ${stroke}/></svg>`;
  if([95,96,99].includes(code)) return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:#E8604C"><path d="M7 13a4 4 0 1 1 1-7.9A5 5 0 0 1 18 7a3.5 3.5 0 0 1-.5 7H7z" ${stroke}/><path d="M13 15l-3 5h3l-2 4" ${stroke}/></svg>`;
  return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:#9AA3BC"><circle cx="12" cy="12" r="8" ${stroke}/></svg>`;
}

function fmtDay(dateStr, idx){
  if(idx===0) return language==='hi' ? "आज" : language==='bn' ? "আজ" : "Today";
  const d = new Date(dateStr+"T00:00:00");
  const locale = language==='hi' ? 'hi-IN' : language==='bn' ? 'bn-IN' : 'en-US';
  return d.toLocaleDateString(locale, { weekday:'short' });
}

function weatherScene(code){
  if([95,96,99].includes(code)) return {kind:'storm', particles:'<i></i><i></i><i></i>', label:'Thunderstorm'};
  if([71,73,75,77,85,86].includes(code)) return {kind:'snow', particles:'<i></i><i></i><i></i><i></i><i></i>', label:'Snow'};
  if([51,53,55,56,57,61,63,65,66,67,80,81,82].includes(code)) return {kind:'rain', particles:'<i></i><i></i><i></i><i></i><i></i><i></i>', label:'Rain'};
  if([45,48].includes(code)) return {kind:'fog', particles:'<i></i><i></i><i></i>', label:'Fog'};
  if([1,2,3].includes(code)) return {kind:'cloudy', particles:'', label:'Cloudy'};
  return {kind:'clear', particles:'', label:'Clear'};
}

/* ---------------- Chat log rendering ---------------- */
function appendMessage(role, text, isError=false){
  const log = document.getElementById('chatLog');
  const div = document.createElement('div');
  div.className = `msg ${role}${isError ? ' error':''}`;
  const roleLabel = role==='user' ? (language==='hi'?'आप':language==='bn'?'আপনি':'You') : 'WeatherGPT';
  div.innerHTML = `<span class="role">${roleLabel}</span>${escapeHtml(text).replace(/\n/g,'<br>')}`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}
function escapeHtml(s){
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function showTyping(){
  const log = document.getElementById('chatLog');
  const div = document.createElement('div');
  div.className = 'typing';
  div.id = 'typingIndicator';
  div.innerHTML = '<span></span><span></span><span></span>';
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}
function hideTyping(){
  const t = document.getElementById('typingIndicator');
  if(t) t.remove();
}

/* ---------------- Disambiguation chips (state -> district) ---------------- */
function renderDisambiguation(disambig){
  const box = document.getElementById('disambig');
  if(!disambig || !disambig.options || !disambig.options.length){
    box.style.display = 'none';
    return;
  }
  const label = document.getElementById('disambigLabel');
  const chips = document.getElementById('disambigChips');

  if(disambig.status === 'need_state'){
    label.textContent = language==='hi'
      ? `"${disambig.query}" नाम की कई जगहें हैं — कौन सा राज्य?`
      : language==='bn'
      ? `"${disambig.query}" নামে একাধিক জায়গা আছে — কোন রাজ্য?`
      : `Multiple places named "${disambig.query}" — which state?`;
    chips.innerHTML = disambig.options.map(s => `<button data-answer="${escapeHtml(s)}">${escapeHtml(s)}</button>`).join('');
  } else if(disambig.status === 'need_district'){
    label.textContent = language==='hi'
      ? `${disambig.state} में कई जगहें हैं — कौन सा ज़िला?`
      : language==='bn'
      ? `${disambig.state}-এ একাধিক জায়গা আছে — কোন জেলা?`
      : `Multiple matches in ${disambig.state} — which district?`;
    chips.innerHTML = disambig.options.map(d => `<button data-answer="${escapeHtml(d)}">${escapeHtml(d)}</button>`).join('');
  } else { // need_choice — full candidate objects
    label.textContent = language==='hi' ? 'सही स्थान चुनें:' : language==='bn' ? 'সঠিক স্থানটি বেছে নিন:' : 'Pick the exact place:';
    chips.innerHTML = disambig.options.map(o => `<button data-answer="${escapeHtml(o.display_name)}">${escapeHtml(o.display_name)}</button>`).join('');
  }
  box.style.display = 'block';
}
document.getElementById('disambigChips').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if(!btn) return;
  document.getElementById('disambig').style.display = 'none';
  handleUserMessage(btn.dataset.answer);
});

/* ---------------- Instrument panel + farmer panel rendering ---------------- */
function riskClass(level){
  return { low:'risk-low', moderate:'risk-moderate', high:'risk-high', severe:'risk-severe' }[level] || 'risk-low';
}

function renderPanel(weatherData){
  lastWeatherData = weatherData;
  const c = weatherData.current;
  const today = weatherData.days[0];
  const advisories = weatherData.advisories || [];
  const scene = weatherScene(c.weather_code);

  const temps = weatherData.days.map(d=>d.temp_max);
  const min = Math.min(...temps), max = Math.max(...temps);
  const range = (max-min)||1;
  const pts = temps.map((t,i)=>{
    const x = (i/(temps.length-1))*260;
    const y = 40 - ((t-min)/range)*32;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  const forecastHtml = weatherData.days.map((d,i)=>`
    <div class="fday">
      <div class="d">${fmtDay(d.date,i)}</div>
      ${weatherIcon(d.weather_code,20)}
      <div class="hi">${d.temp_max}°</div>
      <div class="lo">${d.temp_min}°</div>
    </div>`).join("");

  const sevLabel = (level) => level==='high'
    ? (language==='hi' ? 'उच्च' : language==='bn' ? 'উচ্চ' : 'HIGH')
    : (language==='hi' ? 'मध्यम' : language==='bn' ? 'মাঝারি' : 'MED');

  const advHtml = advisories.length
    ? `<ul>${advisories.map(a=>`<li><span class="adv-badge ${a.level}">${sevLabel(a.level)}</span><b>${a.icon} ${a.title}</b> — ${a.text}</li>`).join("")}</ul>`
    : `<div class="none">${language==='hi' ? "इस समय कोई सक्रिय चेतावनी नहीं।" : language==='bn' ? "এই মুহূর্তে কোনো সক্রিয় সতর্কতা নেই।" : "No active advisories right now."}</div>`;

  document.getElementById('panelContent').innerHTML = `
    <div class="place-row">
      <div><div class="place-name">${weatherData.place}</div></div>
      <div class="place-time">${c.weather_label}</div>
    </div>
    <div class="current-scene ${scene.kind}" aria-label="Current weather: ${c.weather_label}">
      <div class="scene-sky"><span class="scene-sun"></span><span class="scene-cloud"></span><span class="scene-particles">${scene.particles}</span><span class="scene-bolt"></span></div>
      <div class="scene-caption"><strong>${c.weather_label}</strong><span>Current conditions in ${weatherData.place}</span></div>
    </div>
    <div class="reading-strip">
      <div class="reading"><div class="val">${c.temp}°</div><div class="lbl">${language==='hi'?'तापमान':'temp'}</div></div>
      <div class="reading"><div class="val">${c.feels_like}°</div><div class="lbl">${language==='hi'?'महसूस':'feels'}</div></div>
      <div class="reading"><div class="val">${c.humidity}%</div><div class="lbl">${language==='hi'?'नमी':'humidity'}</div></div>
      <div class="reading"><div class="val">${c.wind}</div><div class="lbl">km/h ${language==='hi'?'हवा':'wind'}</div></div>
      <div class="reading"><div class="val">${today ? today.precip_prob : '–'}%</div><div class="lbl">${language==='hi'?'वर्षा':'rain'}</div></div>
    </div>
    <div class="sparkline">
      <div class="cap">${language==='hi'?'7-दिन तापमान रुझान (अधिकतम)':'7-day high temperature trend'}</div>
      <svg width="100%" height="44" viewBox="0 0 260 44" preserveAspectRatio="none">
        <polyline points="${pts}" fill="none" stroke="#E8A33D" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
      </svg>
    </div>
    <div class="forecast-strip">${forecastHtml}</div>
    <div class="advisories">
      <h3>${language==='hi'?'सक्रिय परामर्श':'Active advisories'}</h3>
      ${advHtml}
    </div>
  `;

  // top banner
  const banner = document.getElementById('advisoryBanner');
  const titleEl = document.getElementById('advisoryTitle');
  const text = document.getElementById('advisoryText');
  if(advisories.length){
    const worst = advisories.find(a=>a.level==='high') || advisories[0];
    const bannerLabel = worst.level==='high'
      ? (language==='hi' ? 'उच्च चेतावनी' : language==='bn' ? 'উচ্চ সতর্কতা' : 'HIGH ALERT')
      : (language==='hi' ? 'मौसम परामर्श' : language==='bn' ? 'আবহাওয়া সতর্কতা' : 'WEATHER ADVISORY');
    titleEl.innerHTML = `<span class="adv-badge ${worst.level}">${bannerLabel}</span>${weatherData.place}`;
    text.innerHTML = advisories.map(a=>`<b>${a.icon} ${a.title}:</b> ${a.text}`).join('<br>');
    banner.classList.add('show');
  } else {
    banner.classList.remove('show');
  }

  renderFarmerPanel(weatherData);

  // status + risk badges
  document.getElementById('statusDot').classList.remove('sample');
  document.getElementById('statusText').textContent = strings[language].live;

  const risk = weatherData.risk_index;
  const dot = document.getElementById('riskDot');
  const txt = document.getElementById('riskText');
  dot.className = 'status-dot';
  if(risk && risk.available){
    dot.classList.add(riskClass(risk.level));
    txt.textContent = `risk index: ${risk.level} (${risk.confidence}%)`;
  } else {
    txt.textContent = 'risk index: n/a';
  }
}

function renderFarmerPanel(weatherData){
  const advisory = weatherData.crop_advisory;
  if(!advisory) return;
  const sub = document.getElementById('farmerSub');
  if(sub) sub.textContent = `${advisory.season_label} · ${weatherData.place}`;
  const cropsHtml = advisory.crops.map(c => `
    <div class="crop-card">
      <h4>${c.name}</h4>
      <p>${c.care}</p>
    </div>`).join('');
  const content = document.getElementById('farmerContent');
  if(content){
    content.innerHTML = `
      <div class="crop-grid">${cropsHtml}</div>
      <div class="farm-tip">💡 ${advisory.tip}</div>
    `;
  }
}

/* ---------------- Backend calls ---------------- */
async function callChat(text){
  messages.push({ role: "user", content: text });
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, language })
  });
  if(!res.ok){
    const errText = await res.text().catch(()=>res.statusText);
    throw new Error(errText || `Server error ${res.status}`);
  }
  return res.json();
}

async function handleUserMessage(text){
  appendMessage('user', text);
  const sendBtn = document.getElementById('sendBtn');
  const input = document.getElementById('userInput');
  sendBtn.disabled = true; input.disabled = true;
  showTyping();

  try{
    const data = await callChat(text);
    messages = data.messages;
    hideTyping();
    appendMessage('ai', data.reply_text || '…');
    const engineDot = document.getElementById('engineDot');
    const engineText = document.getElementById('engineText');
    if(data.engine === 'local'){
      engineDot.style.background = 'var(--amber)';
      engineText.textContent = 'engine: local (no API key)';
    } else {
      engineDot.style.background = 'var(--teal)';
      engineText.textContent = 'engine: Claude AI';
    }
    if(data.weather_data){
      renderPanel(data.weather_data);
      lastResolved = { place: data.weather_data.place };
    }
    renderDisambiguation(data.disambiguation);
  }catch(err){
    hideTyping();
    let hint = err.message;
    // A bare "Failed to fetch" is a network/CORS-level failure, not an HTTP error
    // from the backend. The most common cause is opening this page via file://
    // instead of serving it over http, which the backend's CORS policy will reject.
    if(/failed to fetch/i.test(err.message)){
      if(window.location.protocol === 'file:'){
        hint = (language==='hi'
          ? "बैकएंड से संपर्क नहीं हो सका। यह पेज सीधे फ़ाइल के रूप में (file://) खोला गया है — कृपया इसे किसी लोकल वेब सर्वर से खोलें (जैसे: python -m http.server 5500) और फिर http://localhost:5500 पर जाएँ, न कि file:// लिंक पर।"
          : language==='bn'
          ? "ব্যাকএন্ডে সংযোগ করা যায়নি। এই পেজটি সরাসরি ফাইল হিসেবে (file://) খোলা হয়েছে — অনুগ্রহ করে একটি লোকাল ওয়েব সার্ভার দিয়ে খুলুন (যেমন: python -m http.server 5500), তারপর file:// এর বদলে http://localhost:5500 এ যান।"
          : `Couldn't reach the backend. This page is open as a local file (file://), which browsers block from calling ${API_BASE_URL} due to CORS. Serve this folder with a local web server instead — e.g. run "python -m http.server 5500" and open http://localhost:5500, not the file:// path — and make sure the backend allows that origin.`);
      } else {
        hint = (language==='hi'
          ? `बैकएंड (${API_BASE_URL}) से संपर्क नहीं हो सका। जांचें कि सर्वर चल रहा है और CORS में इस पेज के origin (${window.location.origin}) की अनुमति है।`
          : language==='bn'
          ? `ব্যাকএন্ডে (${API_BASE_URL}) সংযোগ করা যায়নি। সার্ভার চলছে কিনা এবং CORS-এ এই পেজের origin (${window.location.origin}) অনুমোদিত কিনা তা যাচাই করুন।`
          : `Couldn't reach the backend at ${API_BASE_URL}. Check that the server is running and that its CORS settings allow this page's origin (${window.location.origin}).`);
      }
    }
    appendMessage('ai', (language==='hi' ? "कुछ गड़बड़ हुई: " : language==='bn' ? "কিছু ভুল হয়েছে: " : "Something went wrong: ") + hint, true);
  } finally {
    sendBtn.disabled = false; input.disabled = false; input.focus();
  }
}

/* ---------------- Wiring ---------------- */
document.getElementById('sendBtn').addEventListener('click', () => {
  const input = document.getElementById('userInput');
  const text = input.value.trim();
  if(!text) return;
  input.value = '';
  handleUserMessage(text);
});
document.getElementById('userInput').addEventListener('keydown', (e) => {
  if(e.key === 'Enter'){ document.getElementById('sendBtn').click(); }
});
document.getElementById('chips').addEventListener('click', (e) => {
  const btn = e.target.closest('.chip');
  if(!btn) return;
  handleUserMessage(btn.dataset.q);
});
document.getElementById('langSeg').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if(!btn) return;
  language = btn.dataset.lang;
  document.querySelectorAll('#langSeg button').forEach(b=>b.classList.toggle('active', b===btn));
  document.getElementById('userInput').placeholder = strings[language].placeholder;
  document.getElementById('sendBtn').textContent = strings[language].send;
  document.getElementById('tagline').textContent = language==='hi'
    ? "संवादात्मक मौसम बुद्धिमत्ता — सरल भाषा में पूर्वानुमान, चेतावनियाँ या जलवायु के बारे में पूछें।"
    : language==='bn'
    ? "কথোপকথনমূলক আবহাওয়া বুদ্ধিমত্তা — সহজ ভাষায় পূর্বাভাস, সতর্কতা বা জলবায়ু নিয়ে জিজ্ঞাসা করুন।"
    : "Conversational weather intelligence — ask about forecasts, alerts, or climate in plain language.";
  // Chat history already contains earlier-language replies; new questions
  // from here on will come back in the newly selected language.
});

// initial greeting
appendMessage('ai', "Namaste! I'm WeatherGPT. Ask me about current conditions, a forecast, or weather alerts for any place — or try one of the suggestions below.");
document.getElementById('statusText').textContent = strings.en.idle;
