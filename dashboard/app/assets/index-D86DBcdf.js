const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/crmView-Djfaj1ay.js","assets/client-AAwCEeoJ.js","assets/jobsView-ChePYY_n.js","assets/urlState-D4h1uWM8.js"])))=>i.map(i=>d[i]);
import{t as e}from"./urlState-D4h1uWM8.js";(function(){let e=document.createElement(`link`).relList;if(e&&e.supports&&e.supports(`modulepreload`))return;for(let e of document.querySelectorAll(`link[rel="modulepreload"]`))n(e);new MutationObserver(e=>{for(let t of e)if(t.type===`childList`)for(let e of t.addedNodes)e.tagName===`LINK`&&e.rel===`modulepreload`&&n(e)}).observe(document,{childList:!0,subtree:!0});function t(e){let t={};return e.integrity&&(t.integrity=e.integrity),e.referrerPolicy&&(t.referrerPolicy=e.referrerPolicy),t.credentials=e.crossOrigin===`use-credentials`?`include`:e.crossOrigin===`anonymous`?`omit`:`same-origin`,t}function n(e){if(e.ep)return;e.ep=!0;let n=t(e);fetch(e.href,n)}})();var t=`modulepreload`,n=function(e){return`/app/`+e},r={},i=function(e){return e.pathname.endsWith(`.css`)},a=function(e,a,o){let s=Promise.resolve();if(a&&a.length>0){let e,c=document.querySelector(`meta[property=csp-nonce]`),l=c?.nonce||c?.getAttribute(`nonce`);function u(e){return Promise.all(e.map(e=>Promise.resolve(e).then(e=>({status:`fulfilled`,value:e}),e=>({status:`rejected`,reason:e}))))}function d(e){return import.meta.resolve?new URL(import.meta.resolve(e)):new URL(e,import.meta.url)}s=u(a.map(a=>{a=n(a,o);let s=d(a);if(s.href in r)return;r[s.href]=!0;let c=i(s);if(e===void 0){e={all:new Set,styles:new Set};let t=document.getElementsByTagName(`link`);for(let n=t.length-1;n>=0;n--){let r=t[n];e.all.add(r.href),r.rel===`stylesheet`&&e.styles.add(r.href)}}if((c?e.styles:e.all).has(s.href))return;let u=document.createElement(`link`);if(u.rel=c?`stylesheet`:t,c||(u.as=`script`),u.crossOrigin=``,u.href=s.href,l&&u.setAttribute(`nonce`,l),document.head.appendChild(u),c)return new Promise((e,t)=>{u.addEventListener(`load`,e),u.addEventListener(`error`,()=>t(Error(`Unable to preload CSS for ${s}`)))})}).filter(e=>e!==void 0))}function c(e){let t=new Event(`vite:preloadError`,{cancelable:!0});if(t.payload=e,window.dispatchEvent(t),!t.defaultPrevented)throw e}return s.then(t=>{for(let e of t||[])e.status===`rejected`&&c(e.reason);return e().catch(c)})};function o(){return new URLSearchParams(window.location.search).get(`view`)===`crm`?`crm`:`jobs`}function s(e,t=!0){let n=new URLSearchParams(window.location.search);e===`crm`?n.set(`view`,`crm`):n.delete(`view`);let r=`${window.location.pathname}${n.toString()?`?${n.toString()}`:``}`;t?window.history.pushState({view:e},``,r):window.history.replaceState({view:e},``,r)}var c=document.querySelector(`#app`);if(!c)throw Error(`Root element #app not found`);c.innerHTML=`
    <div class="kjc-app-shell">
      <header class="kjc-app-header">
        <div class="kjc-app-brand">Karriere Pipeline</div>
        <nav class="kjc-tab-bar" role="tablist" aria-label="Main views">
          <button
            type="button"
            role="tab"
            class="kjc-tab"
            data-view="jobs"
            aria-selected="false"
            aria-controls="jobs-panel"
            id="tab-jobs"
          >
            <span class="kjc-tab-icon" aria-hidden="true">💼</span>
            <span class="kjc-tab-label">Jobs</span>
          </button>
          <button
            type="button"
            role="tab"
            class="kjc-tab"
            data-view="crm"
            aria-selected="false"
            aria-controls="crm-panel"
            id="tab-crm"
          >
            <span class="kjc-tab-icon" aria-hidden="true">👥</span>
            <span class="kjc-tab-label">CRM</span>
          </button>
          <span class="kjc-tab-indicator" aria-hidden="true"></span>
        </nav>
      </header>
      <main class="kjc-app-main" id="kjc-view-container"></main>
    </div>
  `;var l=c.querySelector(`.kjc-tab-bar`),u=c.querySelector(`#kjc-view-container`),d=c.querySelectorAll(`.kjc-tab`),f=c.querySelector(`.kjc-tab-indicator`);function p(e){let t=e.getBoundingClientRect(),n=e.parentElement.getBoundingClientRect();f.style.width=`${t.width}px`,f.style.transform=`translateX(${t.left-n.left}px)`}function m(e){d.forEach(t=>{let n=t.dataset.view===e;t.classList.toggle(`active`,n),t.setAttribute(`aria-selected`,n?`true`:`false`)});let t=l.querySelector(`.kjc-tab[data-view="${e}"]`);t&&p(t)}var h=async t=>{m(t),t===`crm`?await a(async()=>{let{mountCrmView:e}=await import(`./crmView-Djfaj1ay.js`);return{mountCrmView:e}},__vite__mapDeps([0,1])).then(({mountCrmView:e})=>e(u,{q:``,loc:``,date:`all`,exact:``,sort:`date_applied`,dir:`desc`,dataset:``})):await a(async()=>{let{mountJobsView:e}=await import(`./jobsView-ChePYY_n.js`);return{mountJobsView:e}},__vite__mapDeps([2,3,1])).then(({mountJobsView:t})=>t(u,e(window.location.search)))},g=o();m(g),await h(g),l.addEventListener(`click`,e=>{let t=e.target.closest(`.kjc-tab`);if(!t)return;let n=t.dataset.view;n&&(s(n),h(n))}),l.addEventListener(`keydown`,e=>{let t=e.target.closest(`.kjc-tab`);if(!t)return;let n=Array.from(d),r=n.indexOf(t),i=r;if(e.key===`ArrowRight`?(i=(r+1)%n.length,e.preventDefault()):e.key===`ArrowLeft`?(i=(r-1+n.length)%n.length,e.preventDefault()):e.key===`Home`?(i=0,e.preventDefault()):e.key===`End`&&(i=n.length-1,e.preventDefault()),i!==r){let e=n[i];e.focus();let t=e.dataset.view;s(t),h(t)}}),window.addEventListener(`popstate`,e=>{let t=e.state?.view??o();m(t),h(t)}),window.addEventListener(`resize`,()=>{let e=l.querySelector(`.kjc-tab.active`);e&&p(e)});