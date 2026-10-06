import{t as e}from"./client-AAwCEeoJ.js";var t=[{key:`select`,label:``,sortable:!1,className:`kjc-col-select`},{key:`company`,label:`Company`,sortable:!0,className:`kjc-col-title`},{key:`position`,label:`Position`,sortable:!0,className:`kjc-col-company`},{key:`status`,label:`Status`,sortable:!0,className:`kjc-col-status`,render:e=>e.status||`—`},{key:`date_applied`,label:`Applied`,sortable:!0,className:`kjc-col-date`},{key:`source`,label:`Source`,sortable:!1,className:`kjc-col-source`},{key:`actions`,label:`Actions`,sortable:!1,className:`kjc-col-actions`,render:()=>``}];function n(e,t){switch(t){case`status`:return e.status||``;case`date_applied`:return e.date_applied?new Date(e.date_applied).getTime():0;case`source`:return e.source||``;default:return String(e[t]||``).toLowerCase()}}function r(e){return`${e.company}|${e.position}|${e.job_url}`}function i(e){return e.date_applied||`—`}var a=[{label:`Generate Applications`,action:`generate`,icon:`⚙`,requiresSelection:!0},{label:`Open Selected Links`,action:`open`,icon:`↗`,requiresSelection:!0},{label:`Copy Selected`,action:`copy`,icon:`📋`,requiresSelection:!0},{label:`Dismiss Selected`,action:`dismiss`,icon:`🗑`,requiresSelection:!0},{label:`Export Selected (CSV)`,action:`export`,icon:`📥`,requiresSelection:!0}];function o(e,t,n){let r=document.createElement(`div`);r.className=`kjc-batch-dropdown hidden`;let i=document.createElement(`button`);i.type=`button`,i.className=`kjc-btn kjc-batch-trigger`,i.textContent=`Batch Actions ▼`;let o=document.createElement(`div`);return o.className=`kjc-batch-menu hidden`,a.forEach(r=>{let i=document.createElement(`button`);i.type=`button`,i.className=`kjc-batch-item`,i.innerHTML=`<span class="kjc-batch-icon">${r.icon}</span> ${r.label}`,i.addEventListener(`click`,()=>{let i=t();r.requiresSelection&&i.length===0||(e(r,i),n())}),o.appendChild(i)}),r.appendChild(i),r.appendChild(o),i.addEventListener(`click`,e=>{e.stopPropagation(),o.classList.toggle(`hidden`)}),document.addEventListener(`click`,()=>{o.classList.add(`hidden`)}),r}function s(e){return String(e??``).replace(/&/g,()=>`&`).replace(/</g,()=>`<`).replace(/>/g,()=>`>`).replace(/"/g,()=>`"`).replace(/'/g,()=>`'`)}function c(){let t=document.createElement(`aside`);t.className=`kjc-drawer hidden`,t.innerHTML=`
    <div class="kjc-drawer-backdrop" data-role="backdrop"></div>
    <div class="kjc-drawer-panel" role="dialog" aria-modal="true" aria-label="Generate Application">
      <div class="kjc-drawer-head">
        <h2 data-role="title">Generate Application</h2>
        <button type="button" class="kjc-icon-btn" data-role="close" aria-label="Close">✕</button>
      </div>
      <div class="kjc-drawer-body" data-role="body"></div>
    </div>`;let n=t.querySelector(`[data-role="title"]`),r=t.querySelector(`[data-role="body"]`),i=null,a=null,o=()=>{a&&=(clearInterval(a),null),t.classList.add(`hidden`),i=null};t.querySelector(`[data-role="backdrop"]`)?.addEventListener(`click`,o),t.querySelector(`[data-role="close"]`)?.addEventListener(`click`,o),document.addEventListener(`keydown`,e=>{e.key===`Escape`&&!t.classList.contains(`hidden`)&&o()});let c=e=>`
      <div class="kjc-gen-form">
        <div class="kjc-gen-header">
          <h3>${s(e.company)}</h3>
          <p class="kjc-gen-position">${s(e.position)}</p>
        </div>
        <div class="kjc-gen-field">
          <label>Language</label>
          <select data-gen-language>
            <option value="">Auto</option>
            <option value="de">German</option>
            <option value="en">English</option>
          </select>
        </div>
        <div class="kjc-gen-field">
          <label>Cover Letter Tone</label>
          <select data-gen-tone>
            <option value="professional">Professional</option>
            <option value="enthusiastic">Enthusiastic</option>
            <option value="concise">Concise</option>
          </select>
        </div>
        <div class="kjc-gen-actions">
          <button type="button" class="kjc-btn kjc-btn-primary" data-gen-submit>Generate Application</button>
          <button type="button" class="kjc-btn" data-gen-cancel>Cancel</button>
        </div>
        <div class="kjc-gen-status hidden" data-gen-status></div>
      </div>`,l=e=>`
      <div class="kjc-gen-generating">
        <div class="kjc-gen-spinner"></div>
        <p>Generating ATS-tailored application…</p>
        <p class="kjc-gen-task-key">Task: ${s(e)}</p>
        <div class="kjc-gen-progress" data-gen-progress></div>
      </div>`,u=e=>e.status===`already_exists`?`
        <div class="kjc-gen-result success">
          <h4>✓ Application already exists</h4>
          <p>${s(e.message)}</p>
          <div class="kjc-gen-links">
            ${e.cv_path?`<a href="${s(e.cv_path)}" target="_blank" class="kjc-link-btn">Open CV</a>`:``}
            ${e.cover_path?`<a href="${s(e.cover_path)}" target="_blank" class="kjc-link-btn">Open Cover</a>`:``}
          </div>
        </div>`:e.status===`generating`||e.status===`running`?l(e.task_key):`<div class="kjc-gen-result error">Error: ${s(e.message||`Unknown error`)}</div>`,d=async n=>{a&&clearInterval(a);let i=()=>{let e=t.querySelector(`[data-gen-progress]`);e&&(e.textContent=`Processing${`.`.repeat(Date.now()/500%4)}`)};a=window.setInterval(i,500);let o=async()=>{try{let t=await e.generationStatus(n);t.status===`completed`||t.status===`already_exists`||t.status===`error`?(a&&=(clearInterval(a),null),r&&(r.innerHTML=u(t))):i()}catch{i()}};o(),window.setInterval(o,3e3)};return{element:t,open:a=>{if(i=a,!n||!r)return;n.textContent=`Generate: ${s(a.company)} — ${s(a.position)}`,r.innerHTML=c(a);let f=t.querySelector(`[data-gen-submit]`),p=t.querySelector(`[data-gen-cancel]`),m=t.querySelector(`[data-gen-language]`),h=t.querySelector(`[data-gen-status]`);f?.addEventListener(`click`,async()=>{if(!i)return;let t=m?.value||void 0;h&&h.classList.add(`hidden`);try{f&&(f.disabled=!0);let n=await e.generateApplication({company:i.company,position:i.position,description:i.description||``,job_url:i.job_url,location:i.location||``,language:t});n.status===`generating`||n.status===`running`?(r&&(r.innerHTML=l(n.task_key)),await d(n.task_key)):r&&(r.innerHTML=u(n))}catch(e){h&&(h.classList.remove(`hidden`),h.textContent=`Error: ${e instanceof Error?e.message:String(e)}`),r&&(r.innerHTML=c(a))}finally{f&&(f.disabled=!1)}}),p?.addEventListener(`click`,o),t.classList.remove(`hidden`)},close:o}}var l=200,u=480,d=[[`all`,`All Time`],[`today`,`Today Only`],[`2d`,`Last 2 Days`],[`3d`,`Last 3 Days`],[`7d`,`Last 7 Days`],[`14d`,`Last 14 Days`],[`30d`,`Last 30 Days`]];function f(e,t,n){let r=document.createElement(e);return t&&(r.className=t),n!==void 0&&(r.textContent=n),r}async function p(a,s){let p={...s},m=[],h=[],g=new Set,_;a.innerHTML=`
    <div class="kjc-shell">
      <header class="kjc-header">
        <div class="kjc-brand">Karriere Pipeline <span>CRM</span></div>
        <div class="kjc-toolbar">
          <label class="kjc-field">Dataset
            <select id="kjc-dataset"></select>
          </label>
          <span class="kjc-counts" id="kjc-counts">Showing 0 of 0 applications</span>
        </div>
      </header>
      <div class="kjc-filters">
        <input id="kjc-q" type="search" placeholder="Company, position, notes..." />
        <input id="kjc-loc" type="search" placeholder="Location..." />
        <select id="kjc-date">
          ${d.map(([e,t])=>`<option value="${e}">${t}</option>`).join(``)}
        </select>
        <input id="kjc-exact" type="date" />
        <button id="kjc-clear" type="button" class="kjc-btn">Clear All</button>
      </div>
      <div class="kjc-selection hidden" id="kjc-selection">
        <span id="kjc-selected-count">0 selected</span>
        <div id="kjc-batch-container"></div>
        <button id="kjc-deselect" type="button" class="kjc-btn">Deselect All</button>
      </div>
      <div class="kjc-status" id="kjc-status"></div>
      <div class="kjc-grid" role="table" aria-label="CRM Applications">
        <div class="kjc-grid-head" id="kjc-grid-head" role="row"></div>
        <div class="kjc-viewport" id="kjc-viewport" role="rowgroup">
          <div class="kjc-spacer" id="kjc-spacer"></div>
          <div class="kjc-rows" id="kjc-rows"></div>
        </div>
      </div>
    </div>`;let v=e=>{let t=a.querySelector(`#${e}`);if(!t)throw Error(`Missing element #${e}`);return t},y=v(`kjc-dataset`),b=v(`kjc-q`),x=v(`kjc-loc`),S=v(`kjc-date`),C=v(`kjc-exact`),w=v(`kjc-clear`),T=v(`kjc-selection`),E=v(`kjc-selected-count`),D=v(`kjc-batch-container`),O=v(`kjc-deselect`),k=v(`kjc-counts`),A=v(`kjc-status`),j=v(`kjc-grid-head`),M=v(`kjc-viewport`),N=v(`kjc-spacer`),P=v(`kjc-rows`),F=o(async(t,n)=>{if(t.action===`generate`)for(let e of n)I.open(e);else if(t.action===`open`)for(let e of n)e.job_url&&window.open(e.job_url,`_blank`,`noopener,noreferrer`);else if(t.action===`copy`){let e=n.map(e=>`${e.company} — ${e.position} (${e.status||`Applied`})`).join(`
`);await navigator.clipboard.writeText(e),A.textContent=`Copied ${n.length} record(s) to clipboard.`}else if(t.action===`dismiss`){for(let t of n)await e.updateApplication({company:t.company,position:t.position,job_url:t.job_url,status:`Dismissed`}),g.delete(r(t));await Y()}else if(t.action===`export`){let e=n.map(e=>`"${e.company}","${e.position}","${e.status||``}","${e.date_applied}","${e.job_url}"`).join(`
`),t=new Blob([`Company,Position,Status,Date Applied,Job URL\n${e}`],{type:`text/csv`}),r=URL.createObjectURL(t),i=document.createElement(`a`);i.href=r,i.download=`crm-export.csv`,i.click(),URL.revokeObjectURL(r)}},()=>Array.from(g).map(e=>m.find(t=>r(t)===e)).filter(Boolean),()=>{});D.appendChild(F);let I=c();a.querySelector(`.kjc-shell`)?.appendChild(I.element);function L(){let e=M.clientHeight||u,t=Math.max(1,Math.ceil(e/44)),n=h.length*44;N.style.height=`${n}px`;let r=M.scrollTop,i=Math.floor(Math.max(0,r)/44),a=Math.max(0,i-6),o=Math.min(h.length,i+t+6),s=document.createDocumentFragment();for(let e=a;e<o;e+=1)s.appendChild(R(h[e],e));P.replaceChildren(s)}function R(e,t){let n=f(`div`,`kjc-row`);n.style.transform=`translateY(${t*44}px)`,n.setAttribute(`role`,`row`);let a=r(e),o=f(`div`,`kjc-cell kjc-col-select`),s=f(`input`);s.type=`checkbox`,s.checked=g.has(a),s.setAttribute(`aria-label`,`Select ${e.company} — ${e.position}`),s.addEventListener(`change`,()=>{s.checked?g.add(a):g.delete(a),W()}),o.appendChild(s);let c=f(`div`,`kjc-cell kjc-col-title`),l=f(`button`,`kjc-link-btn`,String(e.company||``));l.type=`button`,c.appendChild(l);let u=f(`div`,`kjc-cell kjc-col-company`,String(e.position||``)),d=f(`div`,`kjc-cell kjc-col-status`),p=f(`span`,`kjc-status-badge`,String(e.status||`—`));p.style.cssText=z(e.status),d.appendChild(p);let h=f(`div`,`kjc-cell kjc-col-date`,i(e)||`—`),_=f(`div`,`kjc-cell kjc-col-source`,String(e.source||`—`)),v=f(`div`,`kjc-cell kjc-col-actions`);if(e.job_url){let t=f(`a`,`kjc-link-btn`,`Open ↗`);t.href=String(e.job_url),t.target=`_blank`,t.rel=`noopener noreferrer`,v.appendChild(t)}let y=f(`button`,`kjc-btn kjc-btn-sm`,`Generate`);return y.type=`button`,y.addEventListener(`click`,e=>{e.stopPropagation(),I.open(m.find(e=>r(e)===a))}),v.appendChild(y),n.append(o,c,u,d,h,_,v),n}function z(e){let t=(e||``).toLowerCase();return t.includes(`interview`)||t.includes(`offer`)?`background: #10b98122; color: #10b981; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;`:t.includes(`applied`)||t.includes(`submitted`)?`background: #3b82f622; color: #3b82f6; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;`:t.includes(`reject`)||t.includes(`declined`)?`background: #ef444422; color: #ef4444; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;`:t.includes(`dismiss`)?`background: #6b728022; color: #6b7280; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;`:`background: #f59e0b22; color: #f59e0b; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;`}function B(){let e=document.createDocumentFragment();for(let n of t){let t=f(`div`,`kjc-cell ${n.className}`);if(t.setAttribute(`role`,`columnheader`),n.key===`select`){let e=f(`input`);e.type=`checkbox`,e.id=`kjc-select-all`,e.setAttribute(`aria-label`,`Select all rows`),e.addEventListener(`change`,()=>{for(let t of h)e.checked?g.add(r(t)):g.delete(r(t));L(),W()}),t.appendChild(e)}else t.appendChild(f(`span`,void 0,n.label)),n.sortable&&(t.classList.add(`kjc-sortable`),p.sort===n.key&&(t.classList.add(`kjc-active-sort`),t.appendChild(f(`span`,`kjc-sort-icon`,p.dir===`asc`?`▲`:`▼`))),t.addEventListener(`click`,()=>K(n.key)));e.appendChild(t)}j.replaceChildren(e)}function V(e,t){let n=t.q.trim().toLowerCase(),r=t.loc.trim().toLowerCase();return e.filter(e=>!(t.q&&![e.company,e.position,e.notes,e.status,e.source].some(e=>String(e??``).toLowerCase().includes(n))||r&&!String(e.company??``).toLowerCase().includes(r)||t.exact&&e.date_applied!==t.exact))}function H(e,t,r){let i=r===`asc`?1:-1;return[...e].sort((e,r)=>{let a=n(e,t),o=n(r,t);return a<o?-1*i:a>o?1*i:0})}function U(){h=H(V(m,p),p.sort,p.dir),k.textContent=`Showing ${h.length} of ${m.length} applications`,M.scrollTop=0,L(),W()}function W(){let e=g.size;T.classList.toggle(`hidden`,e===0),E.textContent=`${e} selected`;let t=a.querySelector(`#kjc-select-all`);if(t){let e=h.map(r),n=e.filter(e=>g.has(e)).length;t.checked=n>0&&n===e.length,t.indeterminate=n>0&&n<e.length}}function G(){U()}function K(e){p.sort===e?p.dir=p.dir===`asc`?`desc`:`asc`:(p.sort=e,p.dir=e===`date_applied`?`desc`:`asc`),B(),G()}function q(e){_&&clearTimeout(_),_=setTimeout(e,l)}b.value=p.q,x.value=p.loc,S.value=p.date,C.value=p.exact,b.addEventListener(`input`,()=>{q(()=>{p.q=b.value,G()})}),x.addEventListener(`input`,()=>{q(()=>{p.loc=x.value,G()})}),S.addEventListener(`change`,()=>{p.date=S.value,G()}),C.addEventListener(`change`,()=>{p.exact=C.value,G()}),w.addEventListener(`click`,()=>{p.q=``,p.loc=``,p.date=`all`,p.exact=``,b.value=``,x.value=``,S.value=`all`,C.value=``,G()});let J=!1;M.addEventListener(`scroll`,()=>{J||(J=!0,requestAnimationFrame(()=>{J=!1,L()}))}),O.addEventListener(`click`,()=>{g.clear(),L(),W()});async function Y(){A.textContent=`Loading…`,P.replaceChildren(),N.style.height=`0px`;try{m=await e.tracker(),A.textContent=``,U()}catch(e){m=[],h=[],A.textContent=`Failed to load CRM: ${e instanceof Error?e.message:String(e)}`}}B();try{let t=await e.datasets();y.replaceChildren(...t.map(e=>{let t=f(`option`);return t.value=e,t.textContent=e,t})),t.length>0&&!t.includes(p.dataset)&&(p.dataset=t[0]),y.value=p.dataset}catch(e){A.textContent=`Failed to load datasets: ${e instanceof Error?e.message:String(e)}`}await Y()}export{p as mountCrmView};