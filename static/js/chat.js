const log = document.getElementById('log')
const input = document.getElementById('input')
const send = document.getElementById('send')

function timeNow(){
  const d=new Date(); return d.toLocaleTimeString()
}

function addMessage(kind, text){
  const wrap = document.createElement('div')
  const bubble = document.createElement('div')
  bubble.className = 'bubble ' + kind
  bubble.textContent = text
  wrap.appendChild(bubble)
  const meta = document.createElement('div')
  meta.className = 'meta'
  meta.textContent = timeNow()
  wrap.appendChild(meta)
  log.appendChild(wrap)
  log.scrollTop = log.scrollHeight
  return bubble
}

function addLoading(){
  const wrap = document.createElement('div')
  const bubble = document.createElement('div')
  bubble.className = 'bubble bot'
  const loader = document.createElement('span')
  loader.className='loading'
  loader.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>'
  bubble.appendChild(loader)
  wrap.appendChild(bubble)
  const meta = document.createElement('div')
  meta.className='meta'
  meta.textContent = timeNow()
  wrap.appendChild(meta)
  log.appendChild(wrap)
  log.scrollTop = log.scrollHeight
  return bubble
}

async function ragQuery(){
  const qinp = document.getElementById('rag-question')
  // keep for compatibility but prefer using sendMessage with checkbox
  const resBox = document.getElementById('rag-result')
  const question = (document.getElementById('input') && document.getElementById('input').value || '').trim()
  if(!question){ alert('请输入要在知识库中查询的问题'); return }
  if(resBox) resBox.textContent = '正在查询知识库...'
  try{
    const res = await fetch('/rag/query', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question})})
    const j = await res.json()
    if(j.error){
      if(resBox) resBox.textContent = '查询失败: ' + j.error
      return
    }
    const answer = j.answer || ''
    let docsHtml = ''
    if(Array.isArray(j.docs) && j.docs.length){
      docsHtml = '<div style="margin-top:6px;font-weight:600">相关来源</div>'
      for(const d of j.docs){
        const src = d && d.source ? d.source : JSON.stringify(d)
        docsHtml += `<div style="font-size:12px;color:var(--muted);">• ${src}</div>`
      }
    }
    if(window.marked && window.DOMPurify){
      const node = addMessage('bot', '')
      node.innerHTML = DOMPurify.sanitize(marked.parse(answer || ''))
    }else{
      addMessage('bot', answer || '')
    }
    if(resBox) resBox.innerHTML = docsHtml
  }catch(e){
    if(resBox) resBox.textContent = '查询失败，请查看控制台或服务端日志'
    console.error(e)
  }
}

async function sendMessage(){
  const msg = input.value.trim()
  if(!msg) return
  // 显示用户消息立即
  addMessage('user', msg)
  input.value = ''

  const useKnowledge = document.getElementById('use-knowledge') && document.getElementById('use-knowledge').checked
  const resBox = document.getElementById('rag-result')
  console.log('[chat] sendMessage useKnowledge=', useKnowledge)

  if(useKnowledge){
    // 使用知识库查询流程
    if(resBox) resBox.textContent = '正在查询知识库...'
      try{
  console.log('[chat] calling /rag/query with question=', msg)
      const res = await fetch('/rag/query', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question: msg})})
      const j = await res.json()
  console.log('[chat] /rag/query response=', j)
      if(j.error){
        if(resBox) resBox.textContent = '查询失败: ' + j.error
        return
      }
      const answer = j.answer || ''
      if(window.marked && window.DOMPurify){
        const node = addMessage('bot', '')
        node.innerHTML = DOMPurify.sanitize(marked.parse(answer || ''))
      }else{
        addMessage('bot', answer || '')
      }
      // 显示来源
      let docsHtml = ''
      if(Array.isArray(j.docs) && j.docs.length){
        docsHtml = '<div style="margin-top:6px;font-weight:600">相关来源</div>'
        for(const d of j.docs){
          const src = d && d.source ? d.source : JSON.stringify(d)
          docsHtml += `<div style="font-size:12px;color:var(--muted);">• ${src}</div>`
        }
      }
      if(resBox) resBox.innerHTML = docsHtml
    }catch(e){
      if(resBox) resBox.textContent = '查询失败，请查看控制台或服务端日志'
      console.error(e)
    }
  }else{
    // 普通聊天流程
    const loadingBubble = addLoading()
    try{
      // 附带 session_id（若有）
      const payload = { message: msg }
  console.log('[chat] calling /chat with payload=', payload)
      const sid = localStorage.getItem('session_id')
      if(sid) payload.session_id = sid

  const res = await fetch('/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
  const j = await res.json()
  console.debug('[chat] /chat response=', j)
      const content = j.reply || j.error || '无回复'
      // 使用服务器返回的 messages 来回显完整上下文（前端先清空再渲染）
      if(j.messages && Array.isArray(j.messages)){
        log.innerHTML = ''
        for(const m of j.messages){
          const kind = m.role === 'assistant' ? 'bot' : 'user'
          // 使用 marked + DOMPurify 渲染内容
          if(window.marked && window.DOMPurify){
            const node = addMessage(kind, '')
            node.innerHTML = DOMPurify.sanitize(marked.parse(m.content || ''))
          }else{
            addMessage(kind, m.content || '')
          }
        }
      }else{
        // 回退至以前的单条渲染
        if(window.marked && window.DOMPurify){
          const raw = marked.parse(content || '')
          loadingBubble.innerHTML = DOMPurify.sanitize(raw)
        }else{
          loadingBubble.innerHTML = renderMarkdown(content)
        }
      }
      // 保存返回的 session_id
      if(j.session_id) localStorage.setItem('session_id', j.session_id)
    }catch(e){
      loadingBubble.textContent = '请求失败，请稍后再试'
    }
    log.scrollTop = log.scrollHeight
  }
}

send.addEventListener('click', sendMessage)
input.addEventListener('keydown', (e)=>{ if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); sendMessage() } })

// reset 会话
const resetBtn = document.getElementById('reset')
if(resetBtn){
  resetBtn.addEventListener('click', async ()=>{
    const sid = localStorage.getItem('session_id')
    if(!sid){ alert('当前没有会话可重置'); return }
    try{
      const res = await fetch('/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: sid})})
      const j = await res.json()
      if(j.ok){ localStorage.removeItem('session_id'); alert('会话已重置'); log.innerHTML = '' }
      else { alert('无法重置会话') }
    }catch(e){ alert('重置失败') }
  })
}

// 页面加载时回显历史（如果有 session_id）
window.addEventListener('load', async ()=>{
  const sid = localStorage.getItem('session_id')
  if(!sid) return
  try{
    const res = await fetch('/history', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: sid})})
    const j = await res.json()
    if(j.messages && Array.isArray(j.messages)){
      log.innerHTML = ''
      for(const m of j.messages){
        const kind = m.role === 'assistant' ? 'bot' : 'user'
        if(window.marked && window.DOMPurify){
          const node = addMessage(kind, '')
          node.innerHTML = DOMPurify.sanitize(marked.parse(m.content || ''))
        }else{
          addMessage(kind, m.content || '')
        }
      }
    }
  }catch(e){ console.warn('加载历史失败', e) }
})

// RAG 按钮绑定（如果页面存在这些控件）
window.addEventListener('load', ()=>{
  const ragQueryBtn = document.getElementById('rag-query')
  if(ragQueryBtn) ragQueryBtn.addEventListener('click', ragQuery)
})

// 简易 Markdown 渲染器：支持段落、换行、**加粗**、*斜体*、无序列表、```代码块```。
function escapeHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }

function renderMarkdown(md){
  // 先处理代码块
  md = md.replace(/```([\s\S]*?)```/g, function(m, code){ return '<pre><code>'+ escapeHtml(code) +'</code></pre>' })
  // 转义其余文本
  md = escapeHtml(md)
  // 加粗 **text**
  md = md.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  // 斜体 *text*
  md = md.replace(/\*(.*?)\*/g, '<em>$1</em>')
  // 无序列表（行以 - 或 * 开头）
  const lines = md.split(/\r?\n/)
  let out = []
  let inList = false
  for(let line of lines){
    if(/^[\s\-\*]+/.test(line)){
      const item = line.replace(/^[\s\-\*]+/, '')
      if(!inList){ out.push('<ul>'); inList = true }
      out.push('<li>'+ item +'</li>')
    }else{
      if(inList){ out.push('</ul>'); inList = false }
      if(line.trim() === ''){ out.push('<p></p>') } else { out.push('<p>'+ line +'</p>') }
    }
  }
  if(inList) out.push('</ul>')
  return out.join('\n')
}
