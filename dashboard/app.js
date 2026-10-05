/* 
   dashboard/app.js  —  State management, table rendering, filters, sorting, drawer, and AI copier logic
*/

// Safe localStorage wrapper to prevent crashes in strict sandboxed or private browsing contexts
const datasetCache = new Map();

const safeStorage = {
    getItem(key) {
        try {
            return localStorage.getItem(key);
        } catch (e) {
            return this._fallback[key] || null;
        }
    },
    setItem(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (e) {
            this._fallback[key] = String(value);
        }
    },
    removeItem(key) {
        try {
            localStorage.removeItem(key);
        } catch (e) {
            delete this._fallback[key];
        }
    },
    _fallback: {}
};

// Configure API backend location (defaults to window.API_BASE, stored override, or same-origin '')
const API_BASE = window.API_BASE || safeStorage.getItem('karriere_api_base') || '';
window.API_BASE = API_BASE;

function normalizeText(text) {
    if (!text) return "";
    return text.toString().toLowerCase()
        .replace(/\b(gmbh|ag|co|kg|se|inc|corp|ltd|s\.a\.|university|universität|uni|hochschule)\b/g, "")
        .replace(/[^a-z0-9\-]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

function normalizeTitle(title) {
    if (!title) return "";
    return title.toString().toLowerCase()
        .replace(/[^a-z0-9\-]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

// State variables
let state = {
    viewMode: safeStorage.getItem('karriere_view_mode') || 'portal',
    activeBatchKey: '',
    availableBatches: [],
    allJobs: [],
    filteredJobs: [],
    selectedIndices: new Set(), // Store original index (from state.allJobs)
    appliedUrls: new Set(),    // Store applied job URLs
    appliedKeys: new Set(),    // Store normalized title+company keys
    dismissedUrls: new Set(),  // Store dismissed/deleted job URLs
    dismissedKeys: new Set(),  // Store normalized title+company keys of dismissed jobs
    approvedJobKeys: new Set(), // Real AI approved title+company keys
    approvedUrls: new Set(),    // Real AI approved URLs
    activeFile: '',
    sortColumn: 'date_posted',
    sortDirection: 'desc',
    currentPage: 1,
    pageSize: 50,
    viewLayout: safeStorage.getItem('karriere_view_layout') || 'table',
    filters: {
        search: '',
        company: '',
        batch: '',
        location: '',
        dateRange: 'all',
        customDate: '',
        portals: {
            linkedin: true,
            indeed: true,
            ba: true,
            bund: true,
            xing: true,
            personio: true
        }
    }
};

let trackerState = {
    allRecords: [],
    filterDate: '',
    filterSearch: '',
    filterStatus: '',
    showUnopenedOnly: false,
    sortColumn: 'date_applied',
    sortDirection: 'desc',
    openedUrls: new Set(JSON.parse(safeStorage.getItem('crm_opened_urls') || '[]'))
};

let currentBatchIndex = 0;
let BATCH_SIZE = 5;

// UI Elements
const jobsTbody = document.getElementById('jobs-tbody');
const selectAllCheckbox = document.getElementById('select-all-jobs');
const searchInput = document.getElementById('filter-search');
// Company filter removed
const batchSelector = document.getElementById('filter-batch');
const locationInput = document.getElementById('filter-location');
const dateSelector = document.getElementById('filter-date');
const customDateInput = document.getElementById('filter-custom-date');
const linkedinCheckbox = document.getElementById('portal-linkedin');
const indeedCheckbox = document.getElementById('portal-indeed');
const baCheckbox = document.getElementById('portal-ba');

// Selection Bar Elements
const selectionBar = document.getElementById('selection-bar');
const selectedCountLabel = document.getElementById('selected-count');
const btnClearSelection = document.getElementById('btn-clear-selection');

// Drawer Elements
const jobDrawer = document.getElementById('job-drawer');
const drawerOverlay = document.getElementById('drawer-overlay');
const closeDrawerBtn = document.getElementById('btn-close-drawer');
const drawerBody = document.getElementById('drawer-job-details');

// Console Elements
const aiConsole = document.getElementById('ai-console');
const consoleHeader = document.getElementById('ai-console-header');
const btnToggleConsole = document.getElementById('btn-toggle-console');
const consoleSelectedCount = document.getElementById('console-selected-count');
const templateSelect = document.getElementById('prompt-template-select');
const systemTextarea = document.getElementById('prompt-system-text');
const promptPreview = document.getElementById('prompt-preview');
const previewStats = document.getElementById('preview-stats');
const btnCopyPrompt = document.getElementById('btn-copy-prompt-final');

// Counts
const visibleCountLabel = document.getElementById('visible-count');
const totalCountLabel = document.getElementById('total-count');

// Initialize app on load
window.addEventListener('DOMContentLoaded', async () => {
    // Restore filter and tracker states first
    restoreFilterState();

    // Await CSV file list so dropdown is populated before event listeners attach
    await fetchCSVFiles();
    setupEventListeners();
    injectCopyModal();
    initTabSystem();
    // Render portal chips from restored filter state
    renderPortalFilterChips();

    // Auto-restore last active tab
    const activeTab = safeStorage.getItem('crm_active_tab') || 'jobs-view';
    const activeTabBtn = document.querySelector(`.tab-button[data-target="${activeTab}"]`);

    if (activeTab === 'tracker-view') {
        // If tracker-view is active, fetchTrackerData() (triggered by click) will populate appliedUrls too
        if (activeTabBtn) activeTabBtn.click();
    } else {
        // If jobs-view is active, pre-fetch applied URLs for ticks
        fetchAppliedUrlsOnly();
        if (activeTabBtn) activeTabBtn.click();
    }
});

// ─── Mobile-safe Copy Modal ────────────────────────────────────────────────────
function injectCopyModal() {
    if (document.getElementById('copy-fallback-modal')) return;
    const modal = document.createElement('div');
    modal.id = 'copy-fallback-modal';
    modal.style.cssText = `
        display:none; position:fixed; inset:0; z-index:9999;
        background:rgba(0,0,0,0.75); align-items:center; justify-content:center; padding:16px;
    `;
    modal.innerHTML = `
        <div style="background:#1e1e2e; border:1px solid #333; border-radius:12px; padding:20px; width:100%; max-width:560px; max-height:80vh; display:flex; flex-direction:column; gap:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#fff; font-weight:600; font-size:1rem;">📋 Copy manually — select all &amp; copy</span>
                <button id="copy-modal-close" style="background:none; border:none; color:#aaa; font-size:1.4rem; cursor:pointer; line-height:1;">×</button>
            </div>
            <textarea id="copy-modal-text" readonly
                style="flex:1; min-height:260px; background:#111; color:#a7f3d0; border:1px solid #444; border-radius:8px;
                       padding:12px; font-size:0.85rem; font-family:monospace; resize:none; -webkit-user-select:text; user-select:text;">
            </textarea>
            <button id="copy-modal-btn"
                style="background:linear-gradient(135deg,#10b981,#059669); color:#fff; border:none; border-radius:8px;
                       padding:12px 20px; font-size:0.95rem; font-weight:600; cursor:pointer;">
                Tap here then Select All &amp; Copy
            </button>
        </div>
    `;
    document.body.appendChild(modal);

    document.getElementById('copy-modal-close').addEventListener('click', () => {
        modal.style.display = 'none';
    });
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.style.display = 'none';
    });
    document.getElementById('copy-modal-btn').addEventListener('click', () => {
        const ta = document.getElementById('copy-modal-text');
        const isIOS = /ipad|iphone/i.test(navigator.userAgent);
        if (isIOS) {
            const range = document.createRange();
            range.selectNodeContents(ta);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            ta.setSelectionRange(0, ta.value.length);
        } else {
            ta.focus();
            ta.select();
        }
        try {
            const ok = document.execCommand('copy');
            if (ok) {
                showToast('📋 Copied!');
                modal.style.display = 'none';
            } else {
                // Try async as last resort from inside this direct tap handler
                navigator.clipboard && navigator.clipboard.writeText(ta.value)
                    .then(() => { showToast('📋 Copied!'); modal.style.display = 'none'; })
                    .catch(() => { showToast('Long-press the text above and choose Copy'); });
            }
        } catch (_) {
            showToast('Long-press the text above and choose Copy');
        }
    });
}

function showCopyFallbackModal(text) {
    const modal = document.getElementById('copy-fallback-modal');
    const ta = document.getElementById('copy-modal-text');
    ta.value = text;
    modal.style.display = 'flex';
    setTimeout(() => { ta.focus(); ta.select(); try { ta.setSelectionRange(0, ta.value.length); } catch (_) { } }, 150);
}
// ──────────────────────────────────────────────────────────────────────────────

// Setup event handlers
function setupEventListeners() {

    // Dual View Mode: Portals vs Scraper Batches
    const btnModePortal = document.getElementById('btn-mode-portal');
    const btnModeBatch = document.getElementById('btn-mode-batch');
    const batchTimelineSelect = document.getElementById('batch-timeline-select');
    const btnSelectBatchAll = document.getElementById('btn-select-batch-all');
    const btnCopyBatchAi = document.getElementById('btn-copy-batch-ai');

    if (btnModePortal) {
        btnModePortal.addEventListener('click', () => setViewMode('portal'));
    }
    if (btnModeBatch) {
        btnModeBatch.addEventListener('click', () => setViewMode('batch'));
    }

    if (batchTimelineSelect) {
        batchTimelineSelect.addEventListener('change', (e) => {
            state.activeBatchKey = e.target.value;
            state.batchPortalFilter = 'all';
            updateBatchInfoBadges();
            applyFiltersAndRender();
        });
    }

    if (btnSelectBatchAll) {
        btnSelectBatchAll.addEventListener('click', () => {
            state.selectedIndices.clear();
            state.filteredJobs.forEach(job => {
                if (job._originalIndex !== undefined) {
                    state.selectedIndices.add(job._originalIndex);
                }
            });
            if (selectAllCheckbox) selectAllCheckbox.checked = true;
            updateSelectionUI();
            renderTableRowsOnly();
            showToast(`✓ Selected all ${state.filteredJobs.length} jobs in this batch`);
        });
    }

    if (btnCopyBatchAi) {
        btnCopyBatchAi.addEventListener('click', async () => {
            if (!state.filteredJobs || state.filteredJobs.length === 0) {
                showToast('No jobs in this batch to copy', true);
                return;
            }
            state.selectedIndices.clear();
            state.filteredJobs.forEach(job => {
                if (job._originalIndex !== undefined) {
                    state.selectedIndices.add(job._originalIndex);
                }
            });
            if (selectAllCheckbox) selectAllCheckbox.checked = true;
            updateSelectionUI();
            renderTableRowsOnly();

            await copyPromptToClipboard();
        });
    }

    // Custom Dropdown click handlers
    const dropdown = document.getElementById('dataset-dropdown');
    const dropdownTrigger = document.getElementById('dataset-dropdown-trigger');
    const dropdownOptions = document.getElementById('dataset-dropdown-options');

    if (dropdownTrigger && dropdownOptions) {
        dropdownTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdown.classList.toggle('open');
            dropdownOptions.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (dropdown && !dropdown.contains(e.target)) {
                dropdown.classList.remove('open');
                dropdownOptions.classList.add('hidden');
            }
        });
    }

    // Filtering inputs
    searchInput.addEventListener('input', (e) => {
        state.filters.search = e.target.value.toLowerCase().trim();
        applyFiltersAndRender();
    });



    if (batchSelector) {
        batchSelector.addEventListener('change', (e) => {
            state.filters.batch = e.target.value;
            applyFiltersAndRender();
        });
    }



    locationInput.addEventListener('input', (e) => {
        state.filters.location = e.target.value.toLowerCase().trim();
        applyFiltersAndRender();
    });

    dateSelector.addEventListener('change', (e) => {
        state.filters.dateRange = e.target.value;
        customDateInput.value = '';
        state.filters.customDate = '';
        applyFiltersAndRender();
    });

    const handleCustomDateChange = (e) => {
        state.filters.customDate = e.target.value;
        dateSelector.value = 'all';
        state.filters.dateRange = 'all';
        applyFiltersAndRender();
    };
    customDateInput.addEventListener('input', handleCustomDateChange);
    customDateInput.addEventListener('change', handleCustomDateChange);
    customDateInput.addEventListener('click', () => {
        try { customDateInput.showPicker(); } catch (_) { }
    });

    const handlePortalChange = () => {
        state.filters.portals.linkedin = linkedinCheckbox ? linkedinCheckbox.checked : true;
        state.filters.portals.indeed = indeedCheckbox ? indeedCheckbox.checked : true;
        state.filters.portals.ba = baCheckbox ? baCheckbox.checked : true;
        // bund, xing, stepstone are toggled via portal chips only
        applyFiltersAndRender();
    };
    if (linkedinCheckbox) linkedinCheckbox.addEventListener('change', handlePortalChange);
    if (indeedCheckbox) indeedCheckbox.addEventListener('change', handlePortalChange);
    if (baCheckbox) baCheckbox.addEventListener('change', handlePortalChange);

    document.getElementById('btn-clear-filters').addEventListener('click', () => {
        searchInput.value = '';

        if (batchSelector) batchSelector.value = '';
        state.filters.batch = '';
        locationInput.value = '';
        dateSelector.value = 'all';
        customDateInput.value = '';
        if (linkedinCheckbox) linkedinCheckbox.checked = true;
        if (indeedCheckbox) indeedCheckbox.checked = true;
        if (baCheckbox) baCheckbox.checked = true;

        state.filters = {
            search: '',
            company: '',
            location: '',
            dateRange: 'all',
            customDate: '',
            portals: { linkedin: true, indeed: true, ba: true, bund: true, xing: true }
        };
        saveFilterState();
        renderPortalFilterChips();
        applyFiltersAndRender();
    });

    selectAllCheckbox.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        state.selectedIndices.clear();
        currentBatchIndex = 0;
        if (isChecked) {
            state.filteredJobs.forEach(job => {
                state.selectedIndices.add(job._originalIndex);
            });
        }
        updateSelectionUI();
        renderTableRowsOnly();
    });

    btnClearSelection.addEventListener('click', () => {
        state.selectedIndices.clear();
        selectAllCheckbox.checked = false;
        updateSelectionUI();
        renderTableRowsOnly();
    });

    document.querySelectorAll('.jobs-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.sort;
            if (state.sortColumn === col) {
                state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                state.sortColumn = col;
                state.sortDirection = 'desc';
            }
            document.querySelectorAll('.jobs-table th.sortable').forEach(header => {
                const icon = header.querySelector('.sort-icon');
                if (header.dataset.sort === state.sortColumn) {
                    icon.innerHTML = state.sortDirection === 'asc' ? '▲' : '▼';
                    header.classList.add('active-sort');
                } else {
                    icon.innerHTML = '';
                    header.classList.remove('active-sort');
                }
            });
            sortFilteredJobs();
            renderTableRowsOnly();
        });
    });

    document.querySelectorAll('th.tracker-sortable').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.trackerSort;
            if (trackerState.sortColumn === col) {
                trackerState.sortDirection = trackerState.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                trackerState.sortColumn = col;
                trackerState.sortDirection = 'desc';
            }
            applyTrackerFilters();
        });
    });

    closeDrawerBtn.addEventListener('click', closeDrawer);
    drawerOverlay.addEventListener('click', closeDrawer);

    consoleHeader.addEventListener('click', () => {
        aiConsole.classList.toggle('closed');
    });

    if (templateSelect) templateSelect.addEventListener('change', updatePromptPreview);
    if (systemTextarea) systemTextarea.addEventListener('input', updatePromptPreview);

    const batchSizeSelect = document.getElementById('batch-size-select');
    if (batchSizeSelect) {
        batchSizeSelect.addEventListener('change', (e) => {
            BATCH_SIZE = parseInt(e.target.value, 10);
            currentBatchIndex = 0;
            updateBatchUI();
            updatePromptPreview();
        });
    }

    const batchJumpSelect = document.getElementById('batch-jump-select');
    if (batchJumpSelect) {
        batchJumpSelect.addEventListener('change', (e) => {
            currentBatchIndex = parseInt(e.target.value, 10);
            updateBatchUI();
            updatePromptPreview();
        });
    }

    // Bind Copy Buttons to copyPromptToClipboard
    if (btnCopyPrompt) {
        btnCopyPrompt.addEventListener('click', copyPromptToClipboard);
    }
    const btnCopySelected = document.getElementById('btn-copy-selected');
    if (btnCopySelected) {
        btnCopySelected.addEventListener('click', copyPromptToClipboard);
    }

    // CRM filters
    const trackerFilterDate = document.getElementById('tracker-filter-date');
    if (trackerFilterDate) {
        const handleTrackerDateChange = (e) => {
            trackerState.filterDate = e.target.value;
            applyTrackerFilters();
        };
        trackerFilterDate.addEventListener('input', handleTrackerDateChange);
        trackerFilterDate.addEventListener('change', handleTrackerDateChange);
        trackerFilterDate.addEventListener('click', () => {
            try { trackerFilterDate.showPicker(); } catch (_) { }
        });
    }

    const trackerFilterStatus = document.getElementById('tracker-filter-status');
    if (trackerFilterStatus) {
        trackerFilterStatus.addEventListener('change', (e) => {
            trackerState.filterStatus = e.target.value.trim();
            applyTrackerFilters();
        });
    }

    const trackerFilterSearch = document.getElementById('tracker-filter-search');
    if (trackerFilterSearch) {
        trackerFilterSearch.addEventListener('input', (e) => {
            trackerState.filterSearch = e.target.value.toLowerCase().trim();
            applyTrackerFilters();
        });
    }

    const trackerFilterUnopened = document.getElementById('tracker-filter-unopened');
    if (trackerFilterUnopened) {
        trackerFilterUnopened.addEventListener('change', (e) => {
            trackerState.showUnopenedOnly = e.target.checked;
            applyTrackerFilters();
        });
    }

    const btnClearTrackerDate = document.getElementById('btn-clear-tracker-date');
    if (btnClearTrackerDate) {
        btnClearTrackerDate.addEventListener('click', () => {
            if (trackerFilterDate) trackerFilterDate.value = '';
            trackerState.filterDate = '';
            applyTrackerFilters();
        });
    }

    // Mark all as read button
    const btnMarkAllRead = document.getElementById('btn-mark-all-read');
    if (btnMarkAllRead) {
        btnMarkAllRead.addEventListener('click', () => {
            const cleanLink = (l) => {
                if (!l) return '';
                const s = String(l).trim();
                const lower = s.toLowerCase();
                if (lower === '' || lower === 'n/a' || lower === 'null' || lower === 'undefined' || lower === '#') return '';
                return s;
            };
            trackerState.allRecords.forEach(item => {
                const jobUrl = cleanLink(item.job_url);
                const cvPath = cleanLink(item.cv_pdf_path);
                if (jobUrl) trackerState.openedUrls.add(jobUrl);
                if (cvPath) trackerState.openedUrls.add(cvPath);
                // also cover letter path
                if (cvPath) {
                    const clPath = cvPath.replace('_cv.pdf', '_cover.pdf');
                    trackerState.openedUrls.add(clPath);
                }
            });
            safeStorage.setItem('crm_opened_urls', JSON.stringify(Array.from(trackerState.openedUrls)));
            updateUnopenedCount();
            applyTrackerFilters();
            showToast('✓ All links marked as read');
        });
    }

    const btnResetOpened = document.getElementById('btn-reset-opened');
    if (btnResetOpened) {
        btnResetOpened.addEventListener('click', () => {
            trackerState.openedUrls.clear();
            safeStorage.removeItem('crm_opened_urls');
            updateUnopenedCount();
            applyTrackerFilters();
            showToast('✓ All links reset to unread');
        });
    }
}

// Ultra-fast RFC 4180 CSV parser using slice windows (zero-allocation main loop)
function parseCSV(text) {
    if (!text) return [];

    const firstLineEnd = text.indexOf('\n');
    const firstLine = firstLineEnd !== -1 ? text.slice(0, firstLineEnd) : text;
    const delimiterCode = firstLine.includes(';') ? 59 : 44; // ';' or ','

    const rows = [];
    const len = text.length;
    let currentRow = [];
    let start = 0;
    let inQuotes = false;
    let i = 0;
    let hasEscapedQuotes = false;

    while (i < len) {
        const c = text.charCodeAt(i);
        if (c === 34) { // '"'
            if (inQuotes && i + 1 < len && text.charCodeAt(i + 1) === 34) {
                hasEscapedQuotes = true;
                i += 2;
                continue;
            }
            inQuotes = !inQuotes;
            i++;
            continue;
        }
        if (!inQuotes) {
            if (c === delimiterCode) {
                let cell = text.slice(start, i).trim();
                if (cell.charCodeAt(0) === 34 && cell.charCodeAt(cell.length - 1) === 34) {
                    cell = cell.slice(1, -1);
                }
                if (hasEscapedQuotes) cell = cell.replace(/""/g, '"');
                currentRow.push(cell);
                start = i + 1;
                hasEscapedQuotes = false;
            } else if (c === 10 || c === 13) { // \n or \r
                let cell = text.slice(start, i).trim();
                if (cell.charCodeAt(0) === 34 && cell.charCodeAt(cell.length - 1) === 34) {
                    cell = cell.slice(1, -1);
                }
                if (hasEscapedQuotes) cell = cell.replace(/""/g, '"');
                currentRow.push(cell);
                start = (c === 13 && i + 1 < len && text.charCodeAt(i + 1) === 10) ? i + 2 : i + 1;
                hasEscapedQuotes = false;

                if (currentRow.length > 1 || (currentRow.length === 1 && currentRow[0] !== '')) {
                    rows.push(currentRow);
                }
                currentRow = [];
                if (c === 13 && i + 1 < len && text.charCodeAt(i + 1) === 10) i++;
            }
        }
        i++;
    }
    if (start < len) {
        let cell = text.slice(start).trim();
        if (cell.charCodeAt(0) === 34 && cell.charCodeAt(cell.length - 1) === 34) {
            cell = cell.slice(1, -1);
        }
        if (hasEscapedQuotes) cell = cell.replace(/""/g, '"');
        currentRow.push(cell);
    }
    if (currentRow.length > 0 && !(currentRow.length === 1 && currentRow[0] === '')) {
        rows.push(currentRow);
    }
    if (rows.length === 0) return [];

    const headers = rows[0];
    const data = new Array(rows.length - 1);
    const hLen = headers.length;
    for (let r = 1; r < rows.length; r++) {
        const row = rows[r];
        const obj = {};
        for (let h = 0; h < hLen; h++) {
            obj[headers[h]] = row[h] || '';
        }
        data[r - 1] = obj;
    }
    return data;
}


function isJobAiApproved(job) {
    if (!job) return false;
    if (job.gemini_status && String(job.gemini_status).toUpperCase().startsWith('APPROVED')) return true;
    if (job.ai_approved && (String(job.ai_approved).toLowerCase() === 'true' || job.ai_approved === true)) return true;
    if (job.status === 'Approved' || job.gemini_verdict === 'APPROVED') return true;
    
    const title = (job.title || '').trim().toLowerCase();
    const comp = (job.company || '').trim().toLowerCase();
    if (title && comp && state.approvedJobKeys && state.approvedJobKeys.has(title + ":::" + comp)) return true;
    
    const cleanUrl = (job.job_url || job.apply_url || '').split('?')[0].trim();
    if (cleanUrl && state.approvedUrls && state.approvedUrls.has(cleanUrl)) return true;
    
    return false;
}

async function fetchApprovedJobsIndex() {
    try {
        const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        if (isLocal && API_BASE !== undefined) {
            const res = await fetch((API_BASE || '') + '/api/approved-index');
            if (res.ok) {
                const rows = await res.json();
                if (Array.isArray(rows) && rows.length > 0) {
                    rows.forEach(r => {
                        const title = (r.title || '').trim().toLowerCase();
                        const comp = (r.company || '').trim().toLowerCase();
                        if (title && comp) {
                            state.approvedJobKeys.add(title + ":::" + comp);
                        }
                        const cleanUrl = (r.job_url || r.apply_url || '').split('?')[0].trim();
                        if (cleanUrl) {
                            state.approvedUrls.add(cleanUrl);
                        }
                    });
                    console.log("[AI Approved] Indexed " + state.approvedJobKeys.size + " approved jobs from DB");
                }
            }
        }
    } catch (e) {
        console.warn('Could not fetch approved jobs index from DB:', e);
    }
}

// Fetch list of files
async function fetchCSVFiles() {
    const defaultViews = [
        'ai_approved',
        'all_combined',
        'toyath_best_jobs',
        'gemini_filtered_out',
        'linkedin',
        'indeed',
        'ba',
        'bund',
        'xing'
    ];

    let files = defaultViews;
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (isLocal && API_BASE !== undefined) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            const res = await fetch((API_BASE || '') + '/api/datasets', { signal: controller.signal });
            clearTimeout(timeoutId);
            if (res.ok) {
                files = await res.json();
            }
        } catch (e) {
            console.warn('API /api/datasets unavailable, using default views');
        }
    }

    let defaultFile = safeStorage.getItem('karriere_last_csv') || (files.includes('ai_approved') ? 'ai_approved' : (files.includes('ai_approved.csv') ? 'ai_approved.csv' : files[0]));
    populateCustomDropdown(files, defaultFile);
    fetchDismissedJobs();
    await fetchApprovedJobsIndex();
    loadDataset(defaultFile);
}

const DATASET_METADATA = {
    "ai_approved": {
        label: "AI Approved Jobs",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #10B981; flex-shrink: 0;"><path fill="currentColor" d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2zM7.5 13A2.5 2.5 0 0 0 5 15.5 2.5 2.5 0 0 0 7.5 18a2.5 2.5 0 0 0 2.5-2.5A2.5 2.5 0 0 0 7.5 13zm9 0a2.5 2.5 0 0 0-2.5 2.5 2.5 0 0 0 2.5 2.5 2.5 0 0 0 2.5-2.5 2.5 2.5 0 0 0-2.5-2.5z"/></svg>'
    },
    "all_combined": {
        label: "All Jobs Combined",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #38BDF8; flex-shrink: 0;"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>'
    },
    "toyath_best_jobs": {
        label: "Best Matches (>=40%)",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #F59E0B; flex-shrink: 0;"><path fill="currentColor" d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>'
    },
    "gemini_filtered_out": {
        label: "Disqualified Jobs (Gemini)",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #EF4444; flex-shrink: 0;"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8 0-1.85.63-3.55 1.69-4.9L16.9 18.31C15.55 19.37 13.85 20 12 20zm6.31-3.1L7.1 5.69C8.45 4.63 10.15 4 12 4c4.42 0 8 3.58 8 8 0 1.85-.63 3.55-1.69 4.9z"/></svg>'
    },
    "linkedin": {
        label: "LinkedIn",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #0A66C2; flex-shrink: 0;"><path fill="currentColor" d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.32 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.79M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/></svg>'
    },
    "indeed": {
        label: "Indeed",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #2164F3; flex-shrink: 0;"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>'
    },
    "ba": {
        label: "Agentur f. Arbeit",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #E30613; flex-shrink: 0;"><path fill="currentColor" d="M12 3L2 12h3v8h5v-6h4v6h5v-8h3L12 3zm0 7.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/></svg>'
    },
    "bund": {
        label: "Bund.de / ÖD",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #10B981; flex-shrink: 0;"><path fill="currentColor" d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>'
    },
    "xing": {
        label: "XING",
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #026466; flex-shrink: 0;"><path fill="currentColor" d="M18.188 0c-.517 0-.741.325-.927.66 0 0-7.455 13.224-7.702 13.657.015.024 4.919 9.023 4.919 9.023.17.308.436.66.967.66h3.454c.211 0 .375-.078.463-.22.089-.151.089-.346-.009-.536l-4.879-8.916c-.03-.055-.008-.12.032-.191L22.148.74c.09-.16.085-.348-.004-.492C22.055.105 21.895 0 21.688 0h-3.5zm-11.458 4.77c-.508 0-.726.331-.914.665l-3.69 6.425c-.09.155-.09.345 0 .5l5.503 9.605c.088.155.247.235.457.235h3.454c.523 0 .748-.328.934-.666 0 0-5.467-9.529-5.474-9.558l3.66-6.381c.089-.155.084-.345-.005-.49C10.669 4.96 10.51 4.77 10.301 4.77H6.73z"/></svg>'
    }
};

// Also support legacy .csv aliases seamlessly
Object.keys(DATASET_METADATA).forEach(k => {
    if (!k.endsWith('.csv')) {
        DATASET_METADATA[k + '.csv'] = DATASET_METADATA[k];
        DATASET_METADATA[k + '_latest.csv'] = DATASET_METADATA[k];
        DATASET_METADATA[k + '_all_time.csv'] = DATASET_METADATA[k];
    }
});

function populateCustomDropdown(files, selectedFile) {
    const dropdownOptions = document.getElementById('dataset-dropdown-options');
    const selectedLabel = document.getElementById('selected-dataset-label');
    if (!dropdownOptions || !selectedLabel) return;

    dropdownOptions.innerHTML = '';

    const priorityOrder = ['ai_approved', 'all_combined', 'ai_approved.csv', 'all_combined.csv'];
    const sortedFiles = [...new Set([...priorityOrder.filter(f => files.includes(f)), ...files])];

    sortedFiles.forEach(file => {
        const meta = DATASET_METADATA[file] || {
            label: file.replace('.csv', '').replace(/_/g, ' '),
            icon: '<svg viewBox="0 0 24 24" width="16" height="16" style="color: #94A3B8; flex-shrink: 0;"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>'
        };

        const item = document.createElement('div');
        item.className = 'custom-dropdown-option';
        if (file === selectedFile) {
            item.classList.add('selected');
            selectedLabel.innerHTML = `${meta.icon}<span>${meta.label}</span>`;
        }
        item.innerHTML = `${meta.icon}<span>${meta.label}</span>`;
        item.addEventListener('click', () => {
            dropdownOptions.querySelectorAll('.custom-dropdown-option').forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            selectedLabel.innerHTML = `${meta.icon}<span>${meta.label}</span>`;

            const dropdown = document.getElementById('dataset-dropdown');
            if (dropdown) dropdown.classList.remove('open');
            dropdownOptions.classList.add('hidden');

            safeStorage.setItem('karriere_last_csv', file);
            loadDataset(file);
        });
        dropdownOptions.appendChild(item);
    });
}

// Load a specific dataset
async function loadDataset(filename) {
    state.activeFile = filename;

    // Instant in-memory cache return (< 1ms)
    if (datasetCache.has(filename)) {
        const cachedData = datasetCache.get(filename);
        applyLoadedData(cachedData, filename);
        return;
    }

    const displayLabel = (DATASET_METADATA[filename] && DATASET_METADATA[filename].label) ? DATASET_METADATA[filename].label : filename;
    jobsTbody.innerHTML = `
        <tr>
            <td colspan="7" class="loading-state">
                <div class="spinner"></div>
                <p>Loading jobs from ${displayLabel}...</p>
            </td>
        </tr>
    `;

    let data = null;
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000);
        const apiUrl = (window.API_BASE || API_BASE || '') + `/api/jobs?file=${encodeURIComponent(filename)}&t=${Date.now()}`;
        const res = await fetch(apiUrl, { 
            cache: 'no-store',
            signal: controller.signal 
        });
        clearTimeout(timeoutId);
        if (res.ok) {
            data = await res.json();
        }
    } catch (e) {
        console.warn('API fetch failed or unreachable, checking static fallback for:', filename);
    }

    if (!data || data.error) {
        try {
            const csvFilename = filename.endsWith('.csv') ? filename : `${filename}.csv`;
            const candidates = [
                `./data/${csvFilename}`,
                `../data/${csvFilename}`,
                `data/${csvFilename}`,
                `./data/${filename}`,
                `data/${filename}`
            ];
            let csvRes = null;
            for (const path of candidates) {
                try {
                    const r = await fetch(path);
                    if (r.ok) {
                        csvRes = r;
                        break;
                    }
                } catch (_) {}
            }
            if (!csvRes) throw new Error(`Could not load dataset file: ${filename}`);

            const text = await csvRes.text();
            data = parseCSV(text);
        } catch (csvErr) {
            jobsTbody.innerHTML = `
                <tr>
                    <td colspan="7" class="empty-state">
                        <p style="color: var(--accent-red)">❌ Error loading data: ${csvErr.message}</p>
                    </td>
                </tr>
            `;
            showToast('Error loading dataset');
            return;
        }
    }

    if (data && Array.isArray(data)) {
        datasetCache.set(filename, data);
    }
    applyLoadedData(data, filename);
}

function applyLoadedData(data, filename) {
    state.allJobs = data.map((job, idx) => ({
        ...job,
        _originalIndex: idx,
        portal: detectPortal(job.job_url, filename)
    }));

    state.selectedIndices.clear();
    selectAllCheckbox.checked = false;

    populateBatchFilter();
    buildBatchTimeline();
    setViewMode(state.viewMode);
    applyFiltersAndRender();
    updateSelectionUI();
}

function detectPortal(url, filename) {
    if (!url) {
        const fn = (filename || "").toLowerCase();
        if (fn.includes("linkedin")) return "linkedin";
        if (fn.includes("indeed")) return "indeed";
        if (fn.includes("ba") || fn.includes("arbeitsagentur")) return "ba";
        if (fn.includes("bund") || fn.includes("interamt")) return "bund";
        if (fn.includes("xing")) return "xing";
        if (fn.includes("stepstone")) return "stepstone";
        if (fn.includes("personio")) return "personio";
        return "other";
    }
    const u = url.toLowerCase();
    if (u.includes("personio.de") || u.includes("personio.com") || u.includes("jobs.personio")) return "personio";
    if (u.includes("linkedin.com") || u.includes("/jobs/view/")) return "linkedin";
    if (u.includes("indeed.com") || u.includes("indeed.de")) return "indeed";
    if (u.includes("arbeitsagentur.de")) return "ba";
    if (u.includes("bund.de") || u.includes("interamt.de")) return "bund";
    if (u.includes("xing.com")) return "xing";
    if (u.includes("stepstone.de") || u.includes("stepstone.com")) return "stepstone";
    return "other";
}



function getJobBatchDate(job) {
    const raw = (job.evaluated_at || job.scraped_at || job.first_seen || job.date_posted || '').trim();
    if (!raw) return '';
    const m = raw.match(/\d{4}-\d{2}-\d{2}/);
    return m ? m[0] : raw.substring(0, 10);
}

function populateBatchFilter() {
    if (!batchSelector) return;

    // Group jobs by date and portal
    const datePortalCounts = {};
    state.allJobs.forEach(job => {
        const date = getJobBatchDate(job);
        const portal = job.portal || 'other';
        if (date) {
            if (!datePortalCounts[date]) {
                datePortalCounts[date] = { total: 0, portals: {} };
            }
            datePortalCounts[date].total++;
            datePortalCounts[date].portals[portal] = (datePortalCounts[date].portals[portal] || 0) + 1;
        }
    });

    const portalNames = {
        linkedin: '💼 LinkedIn',
        indeed: '🔍 Indeed',
        ba: '🏛️ Bundesagentur (BA)',
        bund: '🏛️ Bund.de / ÖD',
        xing: '🟢 XING',
        personio: '🚀 Personio ATS',
        other: '🌐 Other'
    };

    const sortedDates = Object.keys(datePortalCounts).sort((a, b) => b.localeCompare(a));
    batchSelector.innerHTML = '<option value="">All Batches & Portals</option>';

    sortedDates.forEach(date => {
        const data = datePortalCounts[date];
        const group = document.createElement('optgroup');
        group.label = `📅 ${date} (${data.total} jobs)`;

        // Option for entire date across all portals
        const allOpt = document.createElement('option');
        allOpt.value = date;
        allOpt.textContent = `📅 ${date} — All Portals (${data.total})`;
        group.appendChild(allOpt);

        // Options per portal for this date
        Object.keys(data.portals).sort().forEach(p => {
            const pOpt = document.createElement('option');
            pOpt.value = `${date}:${p}`;
            pOpt.textContent = `  └ ${portalNames[p] || p} (${data.portals[p]} jobs)`;
            group.appendChild(pOpt);
        });

        batchSelector.appendChild(group);
    });
}



// ─── Card View Layout ─────────────────────────────────────────────────────
function setViewLayout(layout) {
    state.viewLayout = layout;
    safeStorage.setItem('karriere_view_layout', layout);
    const tableEl = document.getElementById('jobs-table');
    const gridEl  = document.getElementById('jobs-card-grid');
    const btnT = document.getElementById('btn-layout-table');
    const btnC = document.getElementById('btn-layout-cards');
    if (layout === 'cards') {
        if (btnT) btnT.classList.remove('active'); if (btnC) btnC.classList.add('active');
        if (tableEl) tableEl.style.display = 'none';
        renderCardView();
        updatePaginationUI();
    } else {
        if (btnT) btnT.classList.add('active'); if (btnC) btnC.classList.remove('active');
        if (gridEl) { gridEl.style.display = 'none'; }
        if (tableEl) tableEl.style.display = '';
        renderTableRowsOnly();
        updatePaginationUI();
    }
}

function renderCardView() {
    const tableEl = document.getElementById('jobs-table');
    if (tableEl) tableEl.style.display = 'none';

    let gridEl = document.getElementById('jobs-card-grid');
    if (!gridEl) {
        gridEl = document.createElement('div');
        gridEl.id = 'jobs-card-grid';
        gridEl.className = 'jobs-card-grid';
        const wrapper = document.querySelector('.table-scroll-wrapper');
        if (wrapper) wrapper.insertBefore(gridEl, wrapper.firstChild);
    }
    gridEl.style.display = 'grid';

    const start = (state.currentPage - 1) * state.pageSize;
    const pageJobs = state.filteredJobs.slice(start, start + state.pageSize);

    if (pageJobs.length === 0) {
        gridEl.innerHTML = '<div class="empty-state" style="grid-column:1/-1;padding:60px;text-align:center"><p>No jobs match your filters.</p></div>';
        return;
    }



    const PORTAL_LABEL = { linkedin:'LinkedIn', indeed:'Indeed', ba:'Agentur f.A.', bund:'Bund.de', xing:'XING', stepstone:'StepStone' };
    const PORTAL_COLOR = { linkedin:'#0a66c2', indeed:'#2164f3', ba:'#c62828', bund:'#10b981', xing:'#026466', stepstone:'#008767' };

    gridEl.innerHTML = pageJobs.map(job => {
        const isSelected = state.selectedIndices.has(job._originalIndex);
        const isApplied  = state.appliedUrls.has(job.job_url);
        const gScore = parseInt(job.gemini_score, 10);
        const score  = isNaN(gScore) ? (parseInt(job.score, 10) || 0) : gScore;
        const scoreClass = score >= 85 ? 'card-score-high' : score >= 70 ? 'card-score-mid' : 'card-score-low';
        const chance = job.gemini_interview_chance || '';
        const pLabel = PORTAL_LABEL[job.portal] || job.portal || '';
        const pColor = PORTAL_COLOR[job.portal] || 'var(--text-muted)';
        const skills = (job.gemini_matched_skills || job.matched_skills || '').split(',').filter(Boolean).slice(0, 5)
                           .map(s => '<span class="card-skill-pill">' + escapeHtml(s.trim()) + '</span>').join('');
        const langBadge = job.gemini_doc_language === 'ENGLISH' ? '<span class="card-mini-badge">EN</span>' : '';
        const chanceBadge = chance ? '<span class="card-mini-badge" style="color:' + (chance==='High'?'#34d399':chance==='Medium'?'#f0a93f':'#94a3b8') + '">' + escapeHtml(chance) + '</span>' : '';

        const detectedEmail = detectJobEmail(job);
        const isEmailJob = Boolean(detectedEmail);
        const emailBtn = isEmailJob
            ? '  <button class="card-apply-link" style="border-color: #38bdf8; color: #38bdf8; background: rgba(56, 189, 248, 0.15); cursor: pointer;" onclick="event.stopPropagation(); triggerEmailForJob(' + job._originalIndex + ')" title="Compose Tailored Application Email with Gemini AI (' + escapeHtml(detectedEmail) + ')">✉️ Apply via Email</button>'
            : '  <button class="card-apply-link" style="border-color: #a855f7; color: #a855f7; background: rgba(168, 85, 247, 0.15); cursor: pointer;" onclick="event.stopPropagation(); triggerEmailForJob(' + job._originalIndex + ')" title="Auto-resolve application method and compose email using AI">🤖 AI Composer</button>';

        const portalLinkBtn = (job.job_url && !job.job_url.toLowerCase().startsWith('mailto:'))
            ? '  <a href="' + escapeHtml(job.job_url) + '" target="_blank" class="card-apply-link" style="font-size:0.72rem; color:var(--text-muted); border-color:rgba(255,255,255,0.15);" onclick="event.stopPropagation()" title="View Posting on ' + escapeHtml(pLabel) + '">🔗 ' + (isEmailJob ? escapeHtml(pLabel) : "Apply &rarr;") + '</a>'
            : '';
            
        const generateBtn = '  <button class="card-apply-link" id="gen-btn-' + job._originalIndex + '" style="border-color: #f59e0b; color: #f59e0b; background: rgba(245, 158, 11, 0.15); cursor: pointer; font-weight: 600;" onclick="event.stopPropagation(); generateATSApplication(' + job._originalIndex + ')" title="Generate ATS-Tailored CV & Cover Letter with Gemini AI">⚡ ATS</button>';

        const applyBtn = generateBtn + emailBtn + portalLinkBtn;

        return '<div class="job-card' + (isSelected?' job-card--selected':'') + (isApplied?' job-card--applied':'') + '"' +
               ' data-idx="' + job._originalIndex + '">' +
               '<div class="job-card__top">' +
               '  <span class="job-card__score ' + scoreClass + '">' + (score||'?') + '%</span>' +
               '  <span style="color:' + pColor + ';font-size:0.72rem;font-weight:600">' + escapeHtml(pLabel) + '</span>' +
               '  ' + langBadge + chanceBadge +
               '  <label class="checkbox-container no-text" style="margin-left:auto" onclick="event.stopPropagation()">' +
               '    <input type="checkbox"' + (isSelected?' checked':'') + ' onchange="toggleJobSelection(' + job._originalIndex + ',this.checked)"><span class="checkmark"></span>' +
               '  </label>' +
               '</div>' +
               '<div class="job-card__body" onclick="openDrawer(' + job._originalIndex + ')" style="cursor:pointer">' +
               '  <div class="job-card__title">' + escapeHtml(job.title || 'Unknown Role') + '</div>' +
               '  <div class="job-card__company">' + escapeHtml(job.company || '') + '</div>' +
               '  <div class="job-card__location">' + escapeHtml(job.location || '') + '</div>' +
               (skills ? '  <div class="job-card__skills">' + skills + '</div>' : '') +
               '</div>' +
               '<div class="job-card__footer">' +
               '  <span class="job-card__date">' + escapeHtml(job.date_posted || job.first_seen || '') + '</span>' +
               (isApplied ? '  <span style="color:var(--accent-success);font-size:0.72rem">✓ Applied</span>' : '') +
               applyBtn +
               '</div>' +
               '</div>';
    }).join('');
}

// ── Scraper Batch Timeline & Dual View Mode Logic ──

function extractJobTimestampInfo(job) {
    const raw = (job.scraped_at || job.first_seen || job.evaluated_at || job.date_posted || '').trim();
    if (!raw) return { date: 'Unknown', time: '', epoch: 0 };

    const fullMatch = raw.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (fullMatch) {
        const [, d, h, m, s] = fullMatch;
        const dt = new Date(`${d}T${h}:${m}:${s || '00'}`);
        return {
            date: d,
            time: `${h}:${m}`,
            epoch: isNaN(dt.getTime()) ? 0 : dt.getTime()
        };
    }
    const dateMatch = raw.match(/^(\d{4}-\d{2}-\d{2})/);
    if (dateMatch) {
        const d = dateMatch[1];
        const dt = new Date(`${d}T00:00:00`);
        return {
            date: d,
            time: '',
            epoch: isNaN(dt.getTime()) ? 0 : dt.getTime()
        };
    }
    return { date: raw.substring(0, 10), time: '', epoch: 0 };
}

function extractJobBatchKey(job) {
    if (job._batchKey) return job._batchKey;
    const info = extractJobTimestampInfo(job);
    return info.time ? `${info.date} ${info.time}` : info.date;
}

function isJobDateMatch(job, dateRange, customDate) {
    const jobDateStr = getJobBatchDate(job);
    if (!jobDateStr) return false;
    
    if (customDate) {
        return jobDateStr === customDate;
    }
    if (!dateRange || dateRange === 'all') {
        return true;
    }
    
    const parts = jobDateStr.split('-');
    if (parts.length < 3) return false;
    const [y, m, d] = parts.map(Number);
    if (!y || !m || !d) return false;
    
    const jobDate = new Date(y, m - 1, d);
    jobDate.setHours(0, 0, 0, 0);
    
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    today.setHours(0, 0, 0, 0);
    
    const diffDays = Math.round((today.getTime() - jobDate.getTime()) / (1000 * 60 * 60 * 24));
    
    if (dateRange === 'today') return diffDays === 0;
    if (dateRange === '2d') return diffDays >= 0 && diffDays <= 1;
    if (dateRange === '3d') return diffDays >= 0 && diffDays <= 2;
    if (dateRange === '7d') return diffDays >= 0 && diffDays <= 6;
    if (dateRange === '14d') return diffDays >= 0 && diffDays <= 13;
    if (dateRange === '30d') return diffDays >= 0 && diffDays <= 29;
    return true;
}

function isDateAllowedByFilter(batchDateStr) {
    if (!batchDateStr || batchDateStr === 'Unknown') return true;
    const { dateRange, customDate } = state.filters;
    if (customDate) {
        return batchDateStr === customDate;
    }
    if (dateRange && dateRange !== 'all') {
        const parts = batchDateStr.split('-');
        if (parts.length < 3) return true;
        const [y, m, d] = parts.map(Number);
        if (!y || !m || !d) return true;
        
        const bDate = new Date(y, m - 1, d);
        bDate.setHours(0, 0, 0, 0);
        
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        today.setHours(0, 0, 0, 0);
        
        const diffDays = Math.round((today.getTime() - bDate.getTime()) / (1000 * 60 * 60 * 24));
        if (dateRange === 'today') return diffDays === 0;
        if (dateRange === '2d') return diffDays >= 0 && diffDays <= 1;
        if (dateRange === '3d') return diffDays >= 0 && diffDays <= 2;
        if (dateRange === '7d') return diffDays >= 0 && diffDays <= 6;
        if (dateRange === '14d') return diffDays >= 0 && diffDays <= 13;
        if (dateRange === '30d') return diffDays >= 0 && diffDays <= 29;
    }
    return true;
}

function buildBatchTimeline() {
    // 1. Group jobs by exact timestamp clusters (within 8 minutes on same day belong to same scrape push)
    const items = state.allJobs.map((job, idx) => ({
        idx,
        job,
        info: extractJobTimestampInfo(job)
    }));

    // Sort items by epoch descending
    items.sort((a, b) => b.info.epoch - a.info.epoch);

    const clusters = [];
    items.forEach(item => {
        let matchedCluster = null;
        for (const cl of clusters) {
            if (cl.date === item.info.date) {
                // If both have timestamps and are within 8 mins (480,000 ms)
                if (cl.epoch && item.info.epoch && Math.abs(cl.epoch - item.info.epoch) <= 480000) {
                    matchedCluster = cl;
                    break;
                }
                // If neither has time and dates match
                if (!cl.time && !item.info.time) {
                    matchedCluster = cl;
                    break;
                }
            }
        }

        if (matchedCluster) {
            matchedCluster.items.push(item);
            // Update cluster time to newest in cluster
            if (item.info.epoch > matchedCluster.epoch) {
                matchedCluster.epoch = item.info.epoch;
                matchedCluster.time = item.info.time;
            }
        } else {
            clusters.push({
                date: item.info.date,
                time: item.info.time,
                epoch: item.info.epoch,
                items: [item]
            });
        }
    });

    const batchMap = new Map();
    clusters.forEach(cl => {
        const key = cl.time ? `${cl.date} ${cl.time}` : cl.date;
        const b = {
            key: key,
            label: key,
            date: cl.date,
            time: cl.time,
            total: cl.items.length,
            approvedCount: 0,
            portals: {},
            jobIndices: cl.items.map(it => it.idx)
        };

        cl.items.forEach(it => {
            it.job._batchKey = key;
            const portal = it.job.portal || 'other';
            b.portals[portal] = (b.portals[portal] || 0) + 1;
            if (isJobAiApproved(it.job)) {
                b.approvedCount++;
            }
        });

        batchMap.set(key, b);
    });

    // Sort batches by newest first
    state.availableBatches = Array.from(batchMap.values()).sort((a, b) => b.key.localeCompare(a.key));

    populateBatchTimelineDropdown();
}

function populateBatchTimelineDropdown() {
    const timelineSelect = document.getElementById('batch-timeline-select');
    if (!timelineSelect) return;

    // Filter batches strictly by active date filter (Date Posted or Exact Date)
    const filteredBatches = state.availableBatches.filter(b => isDateAllowedByFilter(b.date));

    const batchCountBadge = document.getElementById('batch-mode-count');
    if (batchCountBadge) {
        batchCountBadge.textContent = filteredBatches.length;
    }

    timelineSelect.innerHTML = '';
    if (filteredBatches.length === 0) {
        timelineSelect.innerHTML = '<option value="">No batches for selected date</option>';
        state.activeBatchKey = '';
        updateBatchInfoBadges();
        return;
    }

    filteredBatches.forEach((b, i) => {
        const opt = document.createElement('option');
        opt.value = b.key;
        const timeStr = b.time ? ` at ${b.time}` : '';
        const portalSummary = Object.keys(b.portals).map(p => `${p.toUpperCase()}: ${b.portals[p]}`).join(', ');
        opt.textContent = `📦 Batch #${i + 1} — ${b.date}${timeStr} (${b.total} jobs · ${portalSummary})`;
        timelineSelect.appendChild(opt);
    });

    if (!state.activeBatchKey || !filteredBatches.some(b => b.key === state.activeBatchKey)) {
        state.activeBatchKey = filteredBatches[0].key;
    }
    timelineSelect.value = state.activeBatchKey;
    updateBatchInfoBadges();
}

function updateBatchInfoBadges() {
    const badgesContainer = document.getElementById('batch-info-badges');
    if (!badgesContainer) return;

    const currentBatch = state.availableBatches.find(b => b.key === state.activeBatchKey);
    if (!currentBatch) {
        badgesContainer.innerHTML = '';
        return;
    }

    const portalIcons = {
        linkedin: "💼 LinkedIn",
        indeed: "🔍 Indeed",
        ba: "🏛️ BA",
        bund: "🏛️ Bund.de",
        xing: "🟢 XING",
        personio: "🚀 Personio",
        other: "🌐 Other"
    };

    const activeFilter = state.batchPortalFilter || 'all';

    let badgesHtml = `
        <span class="batch-info-tag ${activeFilter === 'all' ? 'active' : ''}" data-batch-filter="all" title="Click to view all jobs in this push">
            <strong>${currentBatch.total}</strong> Total Pushed
        </span>
    `;

    Object.entries(currentBatch.portals).forEach(([p, cnt]) => {
        const isActive = activeFilter === p;
        badgesHtml += `
            <span class="batch-info-tag ${isActive ? 'active' : ''}" data-batch-filter="${p}" title="Click to filter ${portalIcons[p] || p} jobs in this batch">
                ${portalIcons[p] || p}: <strong>${cnt}</strong>
            </span>
        `;
    });

    if (currentBatch.approvedCount > 0) {
        const isApprovedActive = activeFilter === 'approved';
        badgesHtml += `
            <span class="batch-info-tag approved ${isApprovedActive ? 'active' : ''}" data-batch-filter="approved" title="Click to filter AI Approved jobs in this batch">
                ⭐ ${currentBatch.approvedCount} AI Approved
            </span>
        `;
    }

    badgesContainer.innerHTML = badgesHtml;

    // Attach click listeners to portal chips in batch bar
    badgesContainer.querySelectorAll('.batch-info-tag').forEach(tag => {
        tag.addEventListener('click', (e) => {
            const filterVal = tag.dataset.batchFilter;
            if (state.batchPortalFilter === filterVal && filterVal !== 'all') {
                state.batchPortalFilter = 'all';
            } else {
                state.batchPortalFilter = filterVal;
            }
            updateBatchInfoBadges();
            applyFiltersAndRender();
        });
    });
}

function renderPortalFilterChips() {
    const container = document.getElementById('portal-chips-container');
    if (!container) return;

    // Count jobs matching current non-portal filters (date, search, location, company, batch)
    const { search, company, location, batch, dateRange, customDate } = state.filters;
    const matchingJobs = state.allJobs.filter(job => {
        if (!isJobDateMatch(job, dateRange, customDate)) return false;
        if (search) {
            const titleMatch = (job.title || '').toLowerCase().includes(search);
            const compMatch = (job.company || '').toLowerCase().includes(search);
            const descMatch = (job.description || '').toLowerCase().includes(search);
            const skillMatch = (job.matched_skills || '').toLowerCase().includes(search);
            if (!titleMatch && !compMatch && !descMatch && !skillMatch) return false;
        }
        if (company && job.company !== company) return false;
        if (location && !(job.location || '').toLowerCase().includes(location)) return false;
        if (batch) {
            const jobBatchDate = getJobBatchDate(job);
            if (batch.includes(':')) {
                const [targetDate, targetPortal] = batch.split(':');
                if (jobBatchDate !== targetDate || job.portal !== targetPortal) return false;
            } else {
                if (jobBatchDate !== batch) return false;
            }
        }
        return true;
    });

    const counts = {
        all: matchingJobs.length,
        linkedin: 0,
        indeed: 0,
        ba: 0,
        bund: 0,
        xing: 0,
        personio: 0,
        other: 0
    };

    matchingJobs.forEach(job => {
        const p = job.portal || 'other';
        counts[p] = (counts[p] || 0) + 1;
    });

    const portalMeta = [
        { id: 'all', label: 'All Portals', count: counts.all, icon: '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>' },
        { id: 'personio', label: 'Personio ATS', count: counts.personio || 0, icon: '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 2.5a5.5 5.5 0 0 1 5.5 5.5c0 2.3-1.4 4.3-3.4 5.1l3.9 7.9c.2.4 0 .9-.4 1.1-.4.2-.9 0-1.1-.4L12.7 14h-1.4l-3.8 7.7c-.2.4-.7.6-1.1.4-.4-.2-.6-.7-.4-1.1l3.9-7.9c-2-.8-3.4-2.8-3.4-5.1 0-3.04 2.46-5.5 5.5-5.5zm0 2C10.07 4.5 8.5 6.07 8.5 8s1.57 3.5 3.5 3.5 3.5-1.57 3.5-3.5-1.57-3.5-3.5-3.5z"/></svg>' },
        { id: 'linkedin', label: 'LinkedIn', count: counts.linkedin, icon: '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.32 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.79M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/></svg>' },
        { id: 'indeed', label: 'Indeed', count: counts.indeed, icon: '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>' },
        { id: 'ba', label: 'Agentur f. Arbeit', count: counts.ba, icon: '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 3L2 12h3v8h5v-6h4v6h5v-8h3L12 3zm0 7.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/></svg>' },
        { id: 'bund', label: 'Bund.de / ÖD', count: counts.bund || 0, icon: '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M12 1L3 5v2h18V5L12 1zm-7 8v8h3V9H5zm5 0v8h3V9h-3zm5 0v8h3V9h-3zm5 0v8h3V9h-3zM2 19v2h20v-2H2z"/></svg>' },
        { id: 'xing', label: 'XING', count: counts.xing || 0, icon: '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M18.188 0c-.517 0-.741.325-.927.652l-5.64 9.943c-.083.14-.14.287-.14.434 0 .15.057.294.14.434l7.466 12.885c.186.327.41.652.927.652h3.986l-7.466-12.885 5.64-9.943c.083-.14.14-.287.14-.434 0-.15-.057-.294-.14-.434h-3.986zm-11.41 4.544c-.517 0-.741.325-.927.652l-2.82 4.972c-.083.14-.14.287-.14.434 0 .15.057.294.14.434l3.733 6.442c.186.327.41.652.927.652h3.986l-3.733-6.442 2.82-4.972c.083-.14.14-.287.14-.434 0-.15-.057-.294-.14-.434h-3.986z"/></svg>' },
    ];

    const allSelected = state.filters.portals.linkedin && state.filters.portals.indeed && state.filters.portals.ba && state.filters.portals.bund && state.filters.portals.xing && state.filters.portals.personio;

    let html = '';
    portalMeta.forEach(p => {
        const isAllChip = p.id === 'all';
        const isActive = isAllChip ? allSelected : !!state.filters.portals[p.id];
        html += `
            <button type="button" class="portal-chip ${p.id} ${isActive ? 'active' : ''}" data-portal="${p.id}" title="${isAllChip ? 'Show all portals' : 'Toggle ' + p.label}">
                ${p.icon}
                <span>${p.label}</span>
                <span class="portal-chip-count">${p.count}</span>
            </button>
        `;
    });

    container.innerHTML = html;

    // Attach multi-select click handlers
    container.querySelectorAll('.portal-chip').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const portalId = btn.dataset.portal;
            if (portalId === 'all') {
                state.filters.portals.linkedin = true;
                state.filters.portals.indeed = true;
                state.filters.portals.ba = true;
                state.filters.portals.bund = true;
                state.filters.portals.xing = true;
                state.filters.portals.personio = true;
            } else {
                if (allSelected) {
                    state.filters.portals.linkedin = false;
                    state.filters.portals.indeed = false;
                    state.filters.portals.ba = false;
                    state.filters.portals.bund = false;
                    state.filters.portals.xing = false;
                    state.filters.portals.personio = false;
                    state.filters.portals[portalId] = true;
                } else {
                    state.filters.portals[portalId] = !state.filters.portals[portalId];
                    const anySelected = Object.values(state.filters.portals).some(Boolean);
                    if (!anySelected) {
                        state.filters.portals.linkedin = true;
                        state.filters.portals.indeed = true;
                        state.filters.portals.ba = true;
                        state.filters.portals.bund = true;
                        state.filters.portals.xing = true;
                        state.filters.portals.personio = true;
                    }
                }
            }
            saveFilterState();
            renderPortalFilterChips();
            applyFiltersAndRender();
        });
    });
}

function setViewMode(mode) {
    state.viewMode = mode;
    safeStorage.setItem('karriere_view_mode', mode);

    const btnPortal = document.getElementById('btn-mode-portal');
    const btnBatch = document.getElementById('btn-mode-batch');
    const portalControlBar = document.getElementById('portal-control-bar');
    const batchControlBar = document.getElementById('batch-control-bar');
    const datasetDropdown = document.getElementById('dataset-dropdown');

    if (mode === 'batch') {
        if (btnPortal) btnPortal.classList.remove('active');
        if (btnBatch) btnBatch.classList.add('active');
        if (portalControlBar) portalControlBar.classList.add('hidden');
        if (batchControlBar) batchControlBar.classList.remove('hidden');
        if (datasetDropdown) datasetDropdown.classList.add('dimmed');
    } else {
        if (btnPortal) btnPortal.classList.add('active');
        if (btnBatch) btnBatch.classList.remove('active');
        if (portalControlBar) portalControlBar.classList.remove('hidden');
        if (batchControlBar) batchControlBar.classList.add('hidden');
        if (datasetDropdown) datasetDropdown.classList.remove('dimmed');
    }

    renderPortalFilterChips();
    applyFiltersAndRender();
}

function applyFiltersAndRender() {
    const { search, company, batch, location, dateRange, customDate, portals } = state.filters;
    state.currentPage = 1;

    state.filteredJobs = state.allJobs.filter(job => {
        // If in Scraper Batch View mode, strictly filter by selected batch & portal chip
        if (state.viewMode === 'batch' && state.activeBatchKey) {
            const jobBatch = extractJobBatchKey(job);
            if (jobBatch !== state.activeBatchKey) return false;

            if (state.batchPortalFilter && state.batchPortalFilter !== 'all') {
                if (state.batchPortalFilter === 'approved') {
                    if (!isJobAiApproved(job)) return false;
                } else {
                    const normPortal = (job.portal || '').toLowerCase();
                    const target = state.batchPortalFilter.toLowerCase();
                    if (target === 'ba' && !normPortal.includes('ba') && !normPortal.includes('arbeitsagentur')) return false;
                    else if (target === 'linkedin' && !normPortal.includes('linkedin')) return false;
                    else if (target === 'indeed' && !normPortal.includes('indeed')) return false;
                    else if (target === 'bund' && !normPortal.includes('bund') && !normPortal.includes('interamt')) return false;
                    else if (target === 'xing' && !normPortal.includes('xing')) return false;
                    else if (target === 'personio' && !normPortal.includes('personio')) return false;
                    else if (target === 'other' && (normPortal.includes('linkedin') || normPortal.includes('indeed') || normPortal.includes('ba') || normPortal.includes('bund') || normPortal.includes('xing') || normPortal.includes('personio'))) return false;
                }
            }
        }
        if (search) {
            const titleMatch = (job.title || '').toLowerCase().includes(search);
            const compMatch = (job.company || '').toLowerCase().includes(search);
            const descMatch = (job.description || '').toLowerCase().includes(search);
            const skillMatch = (job.matched_skills || '').toLowerCase().includes(search);
            if (!titleMatch && !compMatch && !descMatch && !skillMatch) return false;
        }
        if (company && job.company !== company) return false;
        if (batch) {
            const jobBatchDate = getJobBatchDate(job);
            if (batch.includes(':')) {
                const [targetDate, targetPortal] = batch.split(':');
                if (jobBatchDate !== targetDate || job.portal !== targetPortal) return false;
            } else {
                if (jobBatchDate !== batch) return false;
            }
        }
        if (location && !(job.location || '').toLowerCase().includes(location)) return false;



        if (!isJobDateMatch(job, dateRange, customDate)) return false;

        if (job.portal === 'linkedin' && !portals.linkedin) return false;
        if (job.portal === 'indeed' && !portals.indeed) return false;
        if (job.portal === 'ba' && !portals.ba) return false;
        if (job.portal === 'bund' && !portals.bund) return false;
        if (job.portal === 'xing' && !portals.xing) return false;
        if (job.portal === 'personio' && !portals.personio) return false;

        return true;
    });

    syncSelectAllState();
    sortFilteredJobs();
    renderTableRowsOnly();
    visibleCountLabel.textContent = state.filteredJobs.length;
    totalCountLabel.textContent = state.allJobs.length;
    renderPortalFilterChips();
    populateBatchTimelineDropdown();

    // Save filters to localStorage on every change
    saveFilterState();
}

function sortFilteredJobs() {
    const col = state.sortColumn;
    const dir = state.sortDirection === 'asc' ? 1 : -1;

    state.filteredJobs.sort((a, b) => {
        let valA = a[col];
        let valB = b[col];

        if (col === 'score') {
            valA = parseFloat(a.score) || 0;
            valB = parseFloat(b.score) || 0;
        } else if (col === 'date_posted') {
            valA = (a.date_posted || a.first_seen) ? new Date(a.date_posted || a.first_seen) : new Date(0);
            valB = (b.date_posted || b.first_seen) ? new Date(b.date_posted || b.first_seen) : new Date(0);
        } else if (typeof valA === 'string') {
            valA = valA.toLowerCase();
            valB = valB.toLowerCase();
        }

        if (valA < valB) return -1 * dir;
        if (valA > valB) return 1 * dir;
        return 0;
    });
}

function renderTableRowsOnly() {
    if (state.filteredJobs.length === 0) {
        jobsTbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">
                    <p>No jobs match your filter criteria.</p>
                </td>
            </tr>
        `;
        const container = document.getElementById('pagination-controls');
        if (container) container.innerHTML = '';
        return;
    }

    jobsTbody.innerHTML = '';

    const startIdx = (state.currentPage - 1) * state.pageSize;
    const pageJobs = state.filteredJobs.slice(startIdx, startIdx + state.pageSize);

    pageJobs.forEach(job => {
        const tr = document.createElement('tr');
        const isSelected = state.selectedIndices.has(job._originalIndex);
        if (isSelected) tr.classList.add('selected');

                let portalTag = "";
        if (job.portal === "linkedin") {
            portalTag = `<span class="badge-tag source-linkedin" style="display: inline-flex; align-items: center; gap: 4px;">
                <svg viewBox="0 0 24 24" width="12" height="12"><path fill="currentColor" d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.32 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.79M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/></svg>
                LinkedIn
            </span>`;
        } else if (job.portal === "indeed") {
            portalTag = `<span class="badge-tag source-indeed" style="display: inline-flex; align-items: center; gap: 4px;">
                <svg viewBox="0 0 24 24" width="12" height="12"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                Indeed
            </span>`;
        } else if (job.portal === "ba") {
            portalTag = `<span class="badge-tag source-ba" style="display: inline-flex; align-items: center; gap: 4px;">
                <svg viewBox="0 0 24 24" width="12" height="12"><path fill="currentColor" d="M12 3L2 12h3v8h5v-6h4v6h5v-8h3L12 3zm0 7.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/></svg>
                Agentur
            </span>`;
        } else if (job.portal === "bund") {
            portalTag = `<span class="badge-tag" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); display: inline-flex; align-items: center; gap: 4px;">
                <svg viewBox="0 0 24 24" width="12" height="12"><path fill="currentColor" d="M12 1L3 5v2h18V5L12 1zm-7 8v8h3V9H5zm5 0v8h3V9h-3zm5 0v8h3V9h-3zm5 0v8h3V9h-3zM2 19v2h20v-2H2z"/></svg>
                Bund.de
            </span>`;
        } else if (job.portal === "xing") {
            portalTag = `<span class="badge-tag" style="background: rgba(2, 100, 102, 0.2); color: #2dd4bf; border: 1px solid rgba(45, 212, 191, 0.3); display: inline-flex; align-items: center; gap: 4px;">
                <svg viewBox="0 0 24 24" width="12" height="12"><path fill="currentColor" d="M18.188 0c-.517 0-.741.325-.927.652l-5.64 9.943c-.083.14-.14.287-.14.434 0 .15.057.294.14.434l7.466 12.885c.186.327.41.652.927.652h3.986l-7.466-12.885 5.64-9.943c.083-.14.14-.287.14-.434 0-.15-.057-.294-.14-.434h-3.986zm-11.41 4.544c-.517 0-.741.325-.927.652l-2.82 4.972c-.083.14-.14.287-.14.434 0 .15.057.294.14.434l3.733 6.442c.186.327.41.652.927.652h3.986l-3.733-6.442 2.82-4.972c.083-.14.14-.287.14-.434 0-.15-.057-.294-.14-.434h-3.986z"/></svg>
                XING
            </span>`;
        } else if (job.portal === "personio") {
            portalTag = `<span class="badge-tag source-personio" style="background: rgba(99, 102, 241, 0.18); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.35); display: inline-flex; align-items: center; gap: 4px;">
                <svg viewBox="0 0 24 24" width="12" height="12"><path fill="currentColor" d="M12 2.5a5.5 5.5 0 0 1 5.5 5.5c0 2.3-1.4 4.3-3.4 5.1l3.9 7.9c.2.4 0 .9-.4 1.1-.4.2-.9 0-1.1-.4L12.7 14h-1.4l-3.8 7.7c-.2.4-.7.6-1.1.4-.4-.2-.6-.7-.4-1.1l3.9-7.9c-2-.8-3.4-2.8-3.4-5.1 0-3.04 2.46-5.5 5.5-5.5zm0 2C10.07 4.5 8.5 6.07 8.5 8s1.57 3.5 3.5 3.5 3.5-1.57 3.5-3.5-1.57-3.5-3.5-3.5z"/></svg>
                Personio
            </span>`;
        }

        const geminiScore = parseInt(job.gemini_score, 10);
        const scoreVal = isNaN(geminiScore) ? (parseInt(job.score, 10) || 0) : geminiScore;
        const docLang = job.gemini_doc_language || "";
        const interviewChance = job.gemini_interview_chance || "";

        let scoreBadgeHtml = "";
        let langBadgeHtml = "";

        if (docLang === "ENGLISH") {
            langBadgeHtml = `<span class="badge-tag badge-lang-english" title="Apply with English Cover Letter & CV">🇬🇧 English</span>`;
        }

        if (!isNaN(geminiScore) && geminiScore > 0) {
            if (geminiScore >= 85) {
                scoreBadgeHtml = `<span class="badge-tag" style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); font-weight: 700;">⭐ ${geminiScore}% ${interviewChance ? `· ${interviewChance}` : ""}</span>`;
            } else if (geminiScore >= 70) {
                scoreBadgeHtml = `<span class="badge-tag" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); font-weight: 600;">⚡ ${geminiScore}% ${interviewChance ? `· ${interviewChance}` : ""}</span>`;
            } else {
                scoreBadgeHtml = `<span class="badge-tag" style="background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.25);">${geminiScore}%</span>`;
            }
        } else if (isJobAiApproved(job)) {
            scoreBadgeHtml = `<span class="badge-tag" style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); font-weight: 700;">⭐ AI Approved</span>`;
        } else if (scoreVal >= 40) {
            scoreBadgeHtml = `<span class="badge-tag" style="background: rgba(34, 197, 94, 0.18); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.35); font-weight: 700;">⚡ ${scoreVal} pts</span>`;
        } else if (scoreVal >= 20) {
            scoreBadgeHtml = `<span class="badge-tag" style="background: rgba(234, 179, 8, 0.18); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.35); font-weight: 600;">${scoreVal} pts</span>`;
        } else {
            scoreBadgeHtml = `<span class="badge-tag" style="background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.25);">${scoreVal} pts</span>`;
        }

        const matchedSkills = job.gemini_matched_skills || job.matched_skills || "";
        const aiSummary = job.gemini_summary || job.gemini_language_notes || "";
        const aiInsightHtml = aiSummary ? `<span class="ai-insight-badge" data-tooltip="${escapeHtml(aiSummary)}">💡 AI Insight</span>` : "";

        let applicantBadgeHtml = "";
        const appCount = parseInt(job.applicant_count || job.num_applicants || job.applicants, 10);
        if (!isNaN(appCount) && appCount >= 0) {
            if (appCount <= 10) {
                applicantBadgeHtml = `<span class="badge-tag" style="background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); font-weight: 600;" title="Early applicant!"><svg viewBox="0 0 24 24" width="11" height="11" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><path fill="currentColor" d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg>${appCount} applicants</span>`;
            } else if (appCount <= 50) {
                applicantBadgeHtml = `<span class="badge-tag" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-weight: 500;"><svg viewBox="0 0 24 24" width="11" height="11" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><path fill="currentColor" d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg>${appCount} applicants</span>`;
            } else {
                applicantBadgeHtml = `<span class="badge-tag" style="background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3); font-weight: 500;"><svg viewBox="0 0 24 24" width="11" height="11" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><path fill="currentColor" d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg>${appCount} applicants</span>`;
            }
        }

        tr.innerHTML = `
            <td class="col-select cell-select-area" style="cursor: pointer;">
                <label class="checkbox-container no-text" style="pointer-events: none;">
                    <input type="checkbox" data-index="${job._originalIndex}" ${isSelected ? 'checked' : ''}>
                    <span class="checkmark ${job.portal}-chk"></span>
                </label>
            </td>
            <td class="col-title">
                <div class="job-title-container">
                    <span class="job-title-text">${escapeHtml(job.title)}</span>
                    <div class="badge-row">
                        ${portalTag}
                        ${applicantBadgeHtml}
                        ${langBadgeHtml}
                        ${matchedSkills ? `<span class="badge-tag" style="background: rgba(56,189,248,0.15); color: #38BDF8; border:1px solid rgba(56,189,248,0.25)">${escapeHtml(matchedSkills.split(',').slice(0, 3).join(', '))}</span>` : ''}
                        ${aiInsightHtml}
                    </div>
                </div>
            </td>
            <td class="col-company">
                <span class="company-text">${escapeHtml(job.company)}</span>
            </td>
            <td class="col-location">
                <span class="location-text">${escapeHtml(job.location)}</span>
            </td>
            <td class="col-score" style="text-align: center;">
                ${scoreBadgeHtml}
            </td>
            <td class="col-date">
                <span class="date-text">${escapeHtml(job.date_posted || job.first_seen || 'N/A')}</span>
            </td>
            <td class="col-actions" onclick="event.stopPropagation()">
                <div class="job-link-actions">
                <button onclick="generateATSApplication(${job._originalIndex})" class="btn-icon-link job-link-ats" id="table-gen-btn-${job._originalIndex}" style="background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 4px; cursor: pointer; color: #f59e0b; padding: 2px 6px; font-size: 0.72rem; font-weight: 600;" title="Generate ATS-Tailored CV & Cover Letter with Gemini AI">
                    ⚡ ATS
                </button>
                <a href="${job.job_url}" target="_blank" class="btn-icon-link job-link-external" title="Open apply page">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
                </a>
                <button onclick="dismissJob('${escapeHtml(job.job_url)}', '${escapeHtml(job.company)}', '${escapeHtml(job.title)}')" class="btn-icon-link job-link-dismiss" style="background: none; border: none; cursor: pointer; color: var(--text-secondary); opacity: 0.6; padding: 2px;" onmouseover="this.style.opacity='1'; this.style.color='#fca5a5';" onmouseout="this.style.opacity='0.6'; this.style.color='var(--text-secondary)';" title="Dismiss / Hide this job forever">
                    <svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                </button>
                </div>
            </td>
        `;

        tr.addEventListener('click', () => openDrawer(job));

        const chk = tr.querySelector('input[type="checkbox"]');
        chk.addEventListener('change', (e) => {
            toggleJobSelection(job._originalIndex, e.target.checked);
        });

        const tdSelect = tr.querySelector('.cell-select-area');
        tdSelect.addEventListener('click', (e) => {
            e.stopPropagation();
            chk.checked = !chk.checked;
            chk.dispatchEvent(new Event('change'));
        });

        jobsTbody.appendChild(tr);
    });

    renderPaginationControls();
}

function renderPaginationControls() {
    let container = document.getElementById('pagination-controls');
    if (!container) {
        const wrapper = document.querySelector('.table-scroll-wrapper');
        container = document.createElement('div');
        container.id = 'pagination-controls';
        container.className = 'pagination-controls';
        wrapper.parentNode.insertBefore(container, wrapper.nextSibling);
    }

    const totalPages = Math.ceil(state.filteredJobs.length / state.pageSize) || 1;

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <button class="pagination-btn" id="pagination-prev" ${state.currentPage === 1 ? 'disabled' : ''}>◀ Prev</button>
        <span class="pagination-info">Page <strong>${state.currentPage}</strong> of <strong>${totalPages}</strong></span>
        <button class="pagination-btn" id="pagination-next" ${state.currentPage === totalPages ? 'disabled' : ''}>Next ▶</button>
    `;

    document.getElementById('pagination-prev').addEventListener('click', () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            renderTableRowsOnly();
            document.querySelector('.table-scroll-wrapper').scrollTop = 0;
        }
    });

    document.getElementById('pagination-next').addEventListener('click', () => {
        if (state.currentPage < totalPages) {
            state.currentPage++;
            renderTableRowsOnly();
            document.querySelector('.table-scroll-wrapper').scrollTop = 0;
        }
    });
}

function syncSelectAllState() {
    if (state.filteredJobs.length === 0) {
        selectAllCheckbox.checked = false;
        return;
    }
    selectAllCheckbox.checked = state.filteredJobs.every(job => state.selectedIndices.has(job._originalIndex));
}

function toggleJobSelection(index, isChecked) {
    if (isChecked) {
        state.selectedIndices.add(index);
        const job = state.allJobs.find(j => j._originalIndex === index);
        if (job && job.job_url && (!job.description || job.description === '')) {
            fetch(API_BASE + `/api/job-descriptions?file=${encodeURIComponent(state.activeFile)}&urls=${encodeURIComponent(job.job_url)}`)
                .then(res => res.json())
                .then(data => {
                    if (data[job.job_url]) {
                        job.description = data[job.job_url];
                        updatePromptPreview();
                    }
                })
                .catch(err => console.error("Error pre-fetching job description:", err));
        }
    } else {
        state.selectedIndices.delete(index);
    }

    const rowCheckbox = document.querySelector(`.jobs-table tbody input[data-index="${index}"]`);
    if (rowCheckbox) {
        const row = rowCheckbox.closest('tr');
        if (isChecked) row.classList.add('selected');
        else row.classList.remove('selected');
    }

    syncSelectAllState();
    updateSelectionUI();
}

function updateSelectionUI() {
    const size = state.selectedIndices.size;
    const isTrackerView = !document.getElementById('tracker-view').classList.contains('hidden');

    if (size > 0 && !isTrackerView) {
        selectionBar.classList.remove('hidden');
        selectedCountLabel.textContent = size;
        aiConsole.classList.remove('hidden');
        aiConsole.classList.remove('closed');
    } else {
        selectionBar.classList.add('hidden');
        if (size === 0) {
            selectAllCheckbox.checked = false;
        }
        aiConsole.classList.add('hidden');
        aiConsole.classList.add('closed');
    }

    consoleSelectedCount.textContent = size;
    btnCopyPrompt.disabled = size === 0;

    currentBatchIndex = 0;
    updateBatchUI();
    updatePromptPreview();
}

function updateBatchUI() {
    const size = state.selectedIndices.size;
    const btnText = document.getElementById('copy-btn-text');
    const jumpSelect = document.getElementById('batch-jump-select');
    const jumpWrapper = document.getElementById('batch-jump-wrapper');
    const btnCopy = document.getElementById('btn-copy-prompt-final');

    if (!btnCopy || !btnText) return;

    if (size === 0) {
        if (btnText) btnText.textContent = "Copy Batch for AI";
        if (jumpWrapper) jumpWrapper.style.display = 'none';
        btnCopy.disabled = true;
        currentBatchIndex = 0;
        return;
    }

    if (jumpSelect) {
        jumpSelect.innerHTML = '';
        for (let i = 0; i < size; i += BATCH_SIZE) {
            const endIdx = Math.min(i + BATCH_SIZE, size);
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = `${i + 1}-${endIdx}`;
            if (i === currentBatchIndex) opt.selected = true;
            jumpSelect.appendChild(opt);
        }
        if (jumpWrapper) jumpWrapper.style.display = size > BATCH_SIZE ? 'block' : 'none';
    }

    btnCopy.disabled = false;

    if (currentBatchIndex >= size) {
        if (btnText) btnText.textContent = "All Jobs Copied!";
        btnCopy.disabled = true;
    } else {
        if (btnText) btnText.textContent = "Copy Batch";
    }
}

function openDrawer(job) {
    if (job === null || job === undefined) return;
    if (typeof job === 'number') {
        job = state.allJobs.find(j => j._originalIndex === job);
    }
    if (!job) return;
    const drawer = document.getElementById('job-drawer');
    const drawerOverlay = document.getElementById('drawer-overlay');
    const drawerBody = document.getElementById('drawer-body');
    if (!drawer || !drawerOverlay || !drawerBody) return;

    drawer.classList.add('open');
    drawerOverlay.classList.add('open');

    if (job.description && String(job.description).trim() !== '') {
        renderDrawerDetails(job);
        return;
    }

    drawerBody.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 16px; padding: 40px 0;">
            <div class="spinner"></div>
            <p style="color: var(--text-secondary); font-size: 0.95rem;">Loading job description...</p>
        </div>
    `;

    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (isLocal && job.job_url) {
        fetch((API_BASE || '') + `/api/job-descriptions?file=${encodeURIComponent(state.activeFile)}&urls=${encodeURIComponent(job.job_url)}`)
            .then(res => res.json())
            .then(data => {
                job.description = data[job.job_url] || 'No description provided in portal listing. Click Apply URL to view full posting.';
                renderDrawerDetails(job);
            })
            .catch(() => {
                job.description = 'Description not provided in portal listing. Click Apply URL to view full posting.';
                renderDrawerDetails(job);
            });
    } else {
        job.description = 'Description not provided in portal listing. Click Apply URL to view full posting.';
        renderDrawerDetails(job);
    }
}

function formatJobDescription(text) {
    if (!text) return '<em style="color:var(--text-muted)">No description available.</em>';
    // Escape HTML first, then restore safe formatting
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    // Bold markdown (**text**)
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Convert bullet lines (- item / * item / • item) to list items
    const lines = html.split('\n');
    let inList = false;
    const result = [];
    for (const line of lines) {
        const trimmed = line.trim();
        const isBullet = /^[-*•]\s+/.test(trimmed);
        const isNumbered = /^\d+\.\s+/.test(trimmed);
        if (isBullet) {
            if (!inList) { result.push('<ul class="desc-list">'); inList = true; }
            result.push('<li>' + trimmed.replace(/^[-*•]\s+/, '') + '</li>');
        } else if (isNumbered) {
            if (!inList) { result.push('<ol class="desc-list">'); inList = true; }
            result.push('<li>' + trimmed.replace(/^\d+\.\s+/, '') + '</li>');
        } else {
            if (inList) { result.push('</ul>'); inList = false; }
            if (trimmed === '') {
                result.push('<br>');
            } else if (/^[A-ZÜÄÖ][\w\s,:]{2,40}:$/.test(trimmed) || trimmed.endsWith(':') && trimmed.length < 60) {
                result.push('<p class="desc-heading">' + trimmed + '</p>');
            } else {
                result.push('<p>' + trimmed + '</p>');
            }
        }
    }
    if (inList) result.push('</ul>');
    return result.join('');
}

function renderDrawerDetails(job) {
    let skillsHTML = '<span class="text-muted" style="font-size:0.9rem">No direct skills parsed.</span>';
    if (job.matched_skills && job.matched_skills.trim()) {
        skillsHTML = job.matched_skills.split(',')
            .map(s => s.trim())
            .filter(Boolean)
            .map(s => `<span class="skill-tag-pill">${escapeHtml(s)}</span>`)
            .join('');
    }

    let aiBlock = '';
    if (job.ai_score || job.ai_reason) {
        aiBlock = `
            <div class="detail-section">
                <h4>AI Insights</h4>
                <div class="meta-grid" style="margin-bottom: 10px;">
                    <div class="meta-item">
                        <span class="meta-label">AI Match Rating</span>
                        <span class="meta-val" style="color: var(--accent-purple); font-weight: 700; font-size:1.1rem">${escapeHtml(job.ai_score || 'N/A')}/10</span>
                    </div>
                </div>
                ${job.ai_reason ? `<div class="detail-reason-box">${escapeHtml(job.ai_reason)}</div>` : ''}
            </div>
        `;
    }

    const compNorm = normalizeText(job.company);
    const posNorm = normalizeTitle(job.title);
    let isApplied = false;
    if (job.job_url && state.appliedUrls && state.appliedUrls.has(job.job_url)) {
        isApplied = true;
    } else if (compNorm && posNorm && state.appliedKeys) {
        for (const key of state.appliedKeys) {
            const [appComp, appPos] = key.split('|||');
            if (posNorm === appPos && (compNorm.includes(appComp) || appComp.includes(compNorm))) {
                isApplied = true;
                break;
            }
        }
    }
    const applyButtonHtml = isApplied
        ? `<button class="btn-secondary" style="border-color: var(--accent-green); color: var(--accent-green); cursor: default;" disabled>✓ Applied</button>`
        : `<button class="btn-primary" style="background: linear-gradient(135deg, var(--accent-green), #059669); border: none;" onclick="applyJobFromDrawer(${job._originalIndex})">Mark Applied</button>`;

            const detectedEmail = detectJobEmail(job);
            const isEmailJob = Boolean(detectedEmail);
            const mailBtn = `
                <button class="btn-primary" style="padding: 10px 18px; background: linear-gradient(135deg, ${isEmailJob ? '#0284c7, #0369a1' : '#7e22ce, #6b21a8'}); border: none; display: inline-flex; align-items: center; gap: 8px;" onclick="triggerEmailForJob(${job._originalIndex})" title="Compose Application Email with Gemini AI (${isEmailJob ? escapeHtml(detectedEmail) : 'Auto-resolve'})">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                    ${isEmailJob ? `Apply via Email` : '🤖 AI Composer'}
                </button>
            `;
            const portalLinkBtn = (job.job_url && !job.job_url.toLowerCase().startsWith('mailto:')) ? `
                <a href="${escapeHtml(job.job_url)}" target="_blank" class="${isEmailJob ? 'btn-secondary' : 'btn-primary'}" style="padding: 10px 16px; display: inline-flex; align-items: center; gap: 6px;">
                    <span>${isEmailJob ? 'View Posting' : 'Apply on Site'}</span>
                    <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
                </a>
            ` : '';
            const mainActionBtn = mailBtn + portalLinkBtn;

            drawerBody.innerHTML = `
                <div class="detail-main-header">
                    <h3 style="font-size: 1.4rem; color: #FFF; font-weight: 700;">${escapeHtml(job.title)}</h3>
                    <div class="detail-company-loc">
                        <span class="company-text" style="color: var(--accent-cyan); font-weight: 600;">${escapeHtml(job.company)}</span>
                        <span class="divider-dot"></span>
                        <span>${escapeHtml(job.location)}</span>
                    </div>
                    <div class="detail-actions-row">
                        <button id="drawer-gen-btn" class="btn-primary" style="padding: 10px 18px; background: linear-gradient(135deg, #f59e0b, #d97706); border: none; display: inline-flex; align-items: center; gap: 8px; font-weight: 600;" onclick="generateATSApplication(${job._originalIndex})" title="Generate ATS-Tailored CV & Cover Letter">
                            <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M7 2v11h3v9l7-12h-4l4-8z"/></svg>
                            ⚡ Generate ATS Application
                        </button>
                        ${mainActionBtn}
                        ${applyButtonHtml}
                        <button class="btn-secondary" onclick="toggleDrawerJobSelection(${job._originalIndex})">
                            ${state.selectedIndices.has(job._originalIndex) ? 'Deselect Job' : 'Select Job'}
                        </button>
                    </div>
                    <div id="gen-status-drawer" style="display:none; margin-top: 8px; padding: 10px 14px; border-radius: 8px; font-size: 0.85rem; line-height: 1.4;"></div>
                </div>

        <div class="meta-grid">
            <div class="meta-item">
                <span class="meta-label">Date Posted</span>
                <span class="meta-val">${escapeHtml(job.date_posted || job.first_seen || 'Unknown')}</span>
            </div>
        </div>

        ${aiBlock}

        <div class="detail-section">
            <h4>Matched Skills</h4>
            <div class="skills-list">
                ${skillsHTML}
            </div>
        </div>

        <div class="detail-section">
            <h4>Full Description</h4>
            <div class="detail-desc-text">${formatJobDescription(job.description || 'No description available for this job.')}</div>
        </div>
    `;
}

window.toggleDrawerJobSelection = function (idx) {
    const isCurrentlyChecked = state.selectedIndices.has(idx);
    toggleJobSelection(idx, !isCurrentlyChecked);
    const btn = drawerBody.querySelector('.detail-actions-row button');
    if (btn) btn.textContent = !isCurrentlyChecked ? 'Deselect Job' : 'Select Job';
};

function closeDrawer() {
    jobDrawer.classList.remove('open');
}

// =====================================================================
// ATS Application Generator — Dashboard Integration
// =====================================================================
window.generateATSApplication = async function(idx) {
    let job = typeof idx === 'object' ? idx : state.allJobs.find(j => j._originalIndex === idx);
    if (!job && typeof idx === 'number') {
        job = state.filteredJobs.find(j => j._originalIndex === idx) || state.allJobs[idx];
    }
    if (!job) {
        alert('Job data not found.');
        return;
    }

    // Auto-fetch full description if missing or short
    let description = (job.description || '').trim();
    if (!description || description.length < 50) {
        if (job.job_url) {
            try {
                const descResp = await fetch((window.API_BASE || API_BASE || '') + `/api/job-descriptions?file=${encodeURIComponent(state.activeFile || '')}&urls=${encodeURIComponent(job.job_url)}`);
                const descData = await descResp.json();
                if (descData && descData[job.job_url]) {
                    job.description = descData[job.job_url];
                    description = job.description;
                }
            } catch (descErr) {
                console.warn('Auto-fetch description failed:', descErr);
            }
        }
    }

    if (!description || description.length < 50) {
        alert('⚠️ Job description is too short or missing.\n\nA full description is required for ATS keyword optimization.');
        return;
    }

    const company = job.company || 'Unknown';
    const position = job.title || 'Unknown';

    // Update UI — card & table buttons
    const cardBtn = document.getElementById('gen-btn-' + idx);
    if (cardBtn) {
        cardBtn.innerHTML = '⏳ Generating...';
        cardBtn.style.borderColor = '#818cf8';
        cardBtn.style.color = '#818cf8';
        cardBtn.style.background = 'rgba(129, 140, 248, 0.15)';
        cardBtn.disabled = true;
    }
    const tableBtn = document.getElementById('table-gen-btn-' + idx);
    if (tableBtn) {
        tableBtn.innerHTML = '⏳ Gen...';
        tableBtn.style.borderColor = '#818cf8';
        tableBtn.style.color = '#818cf8';
        tableBtn.disabled = true;
    }

    // Update UI — drawer button
    const drawerBtn = document.getElementById('drawer-gen-btn');
    if (drawerBtn) {
        drawerBtn.innerHTML = '<svg class="spin" viewBox="0 0 24 24" width="16" height="16"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31 31"/></svg> Analyzing ATS Keywords...';
        drawerBtn.style.background = 'linear-gradient(135deg, #818cf8, #6366f1)';
        drawerBtn.disabled = true;
    }

    // Show status area in drawer
    const statusEl = document.getElementById('gen-status-drawer');
    if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.style.background = 'rgba(129, 140, 248, 0.1)';
        statusEl.style.border = '1px solid rgba(129, 140, 248, 0.3)';
        statusEl.style.color = '#c4b5fd';
        statusEl.innerHTML = '🔍 Reading full job description & extracting ATS keywords...<br>⏱️ This usually takes 30-60 seconds.';
    }

    try {
        // Detect language for the API
        const lang = job.gemini_doc_language === 'ENGLISH' ? 'en' :
                     job.gemini_doc_language === 'GERMAN' ? 'de' : '';

        const response = await fetch((window.API_BASE || API_BASE || '') + '/api/generate-application', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                company: company,
                position: position,
                description: description,
                job_url: job.job_url || '',
                location: job.location || '',
                language: lang
            })
        });

        const data = await response.json();

        if (data.status === 'already_exists') {
            _showGenComplete(idx, data, statusEl, cardBtn, drawerBtn);
            return;
        }

        if (!data.success) {
            _showGenError(idx, data.error || 'Generation failed', statusEl, cardBtn, drawerBtn);
            return;
        }

        // Poll for completion
        const taskKey = data.task_key;
        if (statusEl) {
            statusEl.innerHTML = '⚡ Gemini is crafting your tailored CV & Cover Letter...<br>📝 Optimizing for ATS keywords from the job description...';
        }

        _pollGenerationStatus(taskKey, idx, statusEl, cardBtn, drawerBtn);

    } catch (err) {
        _showGenError(idx, err.message, statusEl, cardBtn, drawerBtn);
    }
};

function _pollGenerationStatus(taskKey, idx, statusEl, cardBtn, drawerBtn) {
    const pollInterval = setInterval(async () => {
        try {
            const resp = await fetch((window.API_BASE || API_BASE || '') + `/api/generate-application/status?task_key=${encodeURIComponent(taskKey)}`);
            const status = await resp.json();

            if (status.status === 'complete') {
                clearInterval(pollInterval);
                _showGenComplete(idx, status.result || status, statusEl, cardBtn, drawerBtn);
            } else if (status.status === 'error') {
                clearInterval(pollInterval);
                _showGenError(idx, status.message || 'Generation failed', statusEl, cardBtn, drawerBtn);
            } else {
                // Still running — update message
                if (statusEl) {
                    statusEl.innerHTML = '⚡ ' + (status.message || 'Generating...') + '<br>⏱️ Please wait...';
                }
            }
        } catch (pollErr) {
            // Network error — keep polling
            console.warn('Poll error:', pollErr);
        }
    }, 3000);

    // Safety timeout after 3 minutes
    setTimeout(() => {
        clearInterval(pollInterval);
        if (statusEl && statusEl.style.display !== 'none') {
            const currentText = statusEl.innerHTML;
            if (currentText.includes('Generating') || currentText.includes('Analyzing') || currentText.includes('Please wait')) {
                _showGenError(idx, 'Generation timed out after 3 minutes. Check the server logs.', statusEl, cardBtn, drawerBtn);
            }
        }
    }, 180000);
}

function _showGenComplete(idx, result, statusEl, cardBtn, drawerBtn) {
    const cvPath = result.cv_path || '';
    const coverPath = result.cover_path || '';
    const keywords = (result.ats_keywords || []).slice(0, 8).join(', ');
    const summary = result.summary || result.message || 'Application generated successfully!';

    // Update card & table buttons
    if (cardBtn) {
        cardBtn.innerHTML = '📄 View PDFs';
        cardBtn.style.borderColor = '#34d399';
        cardBtn.style.color = '#34d399';
        cardBtn.style.background = 'rgba(52, 211, 153, 0.15)';
        cardBtn.disabled = false;
        if (cvPath) {
            cardBtn.onclick = function(e) {
                e.stopPropagation();
                window.open('/' + cvPath, '_blank');
            };
        }
    }
    const tableBtn = document.getElementById('table-gen-btn-' + idx);
    if (tableBtn) {
        tableBtn.innerHTML = '📄 PDF';
        tableBtn.style.borderColor = '#34d399';
        tableBtn.style.color = '#34d399';
        tableBtn.style.background = 'rgba(52, 211, 153, 0.15)';
        tableBtn.disabled = false;
        if (cvPath) {
            tableBtn.onclick = function(e) {
                e.stopPropagation();
                window.open('/' + cvPath, '_blank');
            };
        }
    }

    // Update drawer button
    if (drawerBtn) {
        drawerBtn.innerHTML = '✅ Application Ready!';
        drawerBtn.style.background = 'linear-gradient(135deg, #34d399, #059669)';
        drawerBtn.disabled = true;
    }

    // Update status area with PDF links and keywords
    if (statusEl) {
        statusEl.style.background = 'rgba(52, 211, 153, 0.1)';
        statusEl.style.border = '1px solid rgba(52, 211, 153, 0.3)';
        statusEl.style.color = '#d1fae5';

        let linksHtml = '<div style="font-weight: 600; margin-bottom: 6px;">✅ ATS-Tailored Application Generated!</div>';
        linksHtml += '<div style="margin-bottom: 4px; color: #a7f3d0;">' + summary + '</div>';
        if (cvPath) {
            linksHtml += '<a href="/' + cvPath + '" target="_blank" style="color: #34d399; text-decoration: underline; margin-right: 16px;">📄 Open Tailored CV (PDF)</a>';
        }
        if (coverPath) {
            linksHtml += '<a href="/' + coverPath + '" target="_blank" style="color: #34d399; text-decoration: underline;">✉️ Open Cover Letter (PDF)</a>';
        }
        if (keywords) {
            linksHtml += '<div style="margin-top: 8px; font-size: 0.78rem; color: #6ee7b7;">🔑 ATS Keywords: ' + keywords + '</div>';
        }
        statusEl.innerHTML = linksHtml;
    }
}

function _showGenError(idx, errorMsg, statusEl, cardBtn, drawerBtn) {
    if (cardBtn) {
        cardBtn.innerHTML = '⚠️ Retry';
        cardBtn.style.borderColor = '#f87171';
        cardBtn.style.color = '#f87171';
        cardBtn.style.background = 'rgba(248, 113, 113, 0.15)';
        cardBtn.disabled = false;
    }
    const tableBtn = document.getElementById('table-gen-btn-' + idx);
    if (tableBtn) {
        tableBtn.innerHTML = '⚠️ Retry';
        tableBtn.style.borderColor = '#f87171';
        tableBtn.style.color = '#f87171';
        tableBtn.disabled = false;
    }

    if (drawerBtn) {
        drawerBtn.innerHTML = '⚠️ Generation Failed — Click to Retry';
        drawerBtn.style.background = 'linear-gradient(135deg, #f87171, #dc2626)';
        drawerBtn.disabled = false;
    }

    if (statusEl) {
        statusEl.style.background = 'rgba(248, 113, 113, 0.1)';
        statusEl.style.border = '1px solid rgba(248, 113, 113, 0.3)';
        statusEl.style.color = '#fca5a5';
        statusEl.innerHTML = '❌ ' + errorMsg;
    }
}

function cleanDescriptionForAI(text) {
    if (!text) return 'No description provided.';
    const lines = text.split('\n').map(l => l.trim());
    const cleaned = lines.filter(line => {
        if (line.length === 0) return false;
        if (line.startsWith('*') || line.startsWith('-') || line.startsWith('•') || line.match(/^[0-9]+\./)) return true;
        if (line.length > 80) return true;
        if (/[.!?:]$/.test(line)) return true;
        const lower = line.toLowerCase();
        if (lower.includes('require') || lower.includes('muss') || lower.includes('task') || lower.includes('aufgab') || lower.includes('skill')) return true;
        if (line.length < 45) return false;
        return true;
    });
    let result = cleaned.join('\n');
    if (result.length > 20000) {
        result = result.substring(0, 20000) + '\n... [Truncated for length]';
    }
    return result;
}

function generatePromptText() {
    if (state.selectedIndices.size === 0) return '';

    const allSelectedJobs = state.filteredJobs.filter(job => state.selectedIndices.has(job._originalIndex));
    const selectedJobs = allSelectedJobs.slice(currentBatchIndex, currentBatchIndex + BATCH_SIZE);

    if (selectedJobs.length === 0) return '';

    const templateType = templateSelect.value;
    const systemInstruction = systemTextarea.value.trim();

    let output = '';
    if (systemInstruction && templateType !== 'raw' && templateType !== 'json') {
        output += systemInstruction + "\n\n";
    }

    if (templateType === 'raw') {
        selectedJobs.forEach((job, index) => {
            const absIndex = currentBatchIndex + index + 1;
            if (index > 0) output += "\n\n---\n\n";
            output += `[JOB ${absIndex}]\n`;
            output += `Title: ${job.title}\n`;
            output += `Company: ${job.company}\n`;
            output += `Location: ${job.location || 'N/A'}\n`;
            if (job.job_url) output += `Apply URL: ${job.job_url}\n`;
            const cleanDesc = cleanDescriptionForAI(job.description);
            output += `Description:\n${cleanDesc}`;
        });
    } else if (templateType === 'detailed') {
        output += "Here are the selected job listings details:\n\n";
        selectedJobs.forEach((job, index) => {
            const absIndex = currentBatchIndex + index + 1;
            output += `=== Job ${absIndex}: ${job.title} at ${job.company} ===\n`;
            output += `- Company: ${job.company}\n`;
            output += `- Location: ${job.location || 'N/A'}\n`;
            if (job.ai_score) output += `- AI Score Match: ${job.ai_score}/10\n`;
            if (job.ai_reason) output += `- AI Evaluation: ${job.ai_reason}\n`;
            if (job.matched_skills) output += `- Matched Skills: ${job.matched_skills}\n`;
            if (job.job_url) output += `- URL: ${job.job_url}\n`;
            const cleanDesc = cleanDescriptionForAI(job.description);
            output += `- Job Description:\n${cleanDesc}\n\n`;
        });
    } else if (templateType === 'compact') {
        output += "Selected Jobs Summary:\n";
        selectedJobs.forEach((job, index) => {
            const absIndex = currentBatchIndex + index + 1;
            let matched = job.matched_skills ? ` | Key Matches: ${job.matched_skills}` : '';
            let aiText = job.ai_score ? ` | AI Score: ${job.ai_score}/10` : '';
            output += `${absIndex}. **${job.title}** at **${job.company}** (${job.location})${aiText}${matched} | Link: ${job.job_url}\n`;
        });
    } else if (templateType === 'json') {
        const cleanJobs = selectedJobs.map(({ _originalIndex, portal, ...rest }) => rest);
        output += JSON.stringify(cleanJobs, null, 2);
    }

    return output;
}

function updatePromptPreview() {
    const text = generatePromptText();
    const templateType = templateSelect.value;

    const headerContainer = document.getElementById('prompt-header-container');
    if (headerContainer) {
        headerContainer.style.display = (templateType === 'raw' || templateType === 'json') ? 'none' : 'flex';
    }

    if (!text) {
        promptPreview.textContent = 'No jobs selected. Select jobs from the spreadsheet above to generate text preview.';
        promptPreview.style.color = 'var(--text-muted)';
        previewStats.textContent = '0 chars';
        return;
    }

    promptPreview.textContent = text;
    promptPreview.style.color = '#A7F3D0';
    previewStats.textContent = `${text.length} chars | ${text.split(/\s+/).length} words`;
}

// ── Copy logic: sync-first strategy for mobile compatibility ──────────────────
async function copyPromptToClipboard() {
    const btnCopy = document.getElementById('btn-copy-prompt-final');
    const allSelectedJobs = state.filteredJobs.filter(job => state.selectedIndices.has(job._originalIndex));
    const currentBatch = allSelectedJobs.slice(currentBatchIndex, currentBatchIndex + BATCH_SIZE);

    if (currentBatch.length === 0) return;

    const missingUrls = currentBatch
        .filter(j => !j.description || String(j.description).trim() === '')
        .map(j => j.job_url)
        .filter(Boolean);

    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    if (missingUrls.length > 0 && isLocal) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 6000);
            const res = await fetch((API_BASE || '') + `/api/job-descriptions?file=${encodeURIComponent(state.activeFile)}&urls=${encodeURIComponent(missingUrls.join(','))}`, { signal: controller.signal });
            clearTimeout(timeoutId);
            if (res.ok) {
                const data = await res.json();
                currentBatch.forEach(j => {
                    if (data[j.job_url]) {
                        j.description = data[j.job_url];
                    }
                });
                updatePromptPreview();
            }
        } catch (e) {
            console.warn('Optional description fetch skipped:', e);
        }
    }

    // Graceful fallback: never block batch copying if a description was empty
    currentBatch.forEach(j => {
        if (!j.description || String(j.description).trim() === '') {
            j.description = `Titel: ${j.title || 'N/A'}\nUnternehmen: ${j.company || 'N/A'}\nStandort: ${j.location || 'N/A'}\nLink: ${j.job_url || j.apply_url || 'N/A'}`;
        }
    });

    const text = generatePromptText();
    if (!text) return;

    const onSuccess = () => {
        currentBatchIndex += BATCH_SIZE;
        if (currentBatchIndex >= allSelectedJobs.length) {
            state.selectedIndices.clear();
            currentBatchIndex = 0;
            selectAllCheckbox.checked = false;
            renderTableRowsOnly();
        }
        updateBatchUI();
        updatePromptPreview();
        onCopySuccess();
    };

    if (execCommandCopy(text)) {
        onSuccess();
        return;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => onSuccess())
            .catch(() => showCopyFallbackModal(text));
        return;
    }

    showCopyFallbackModal(text);
}

function execCommandCopy(text) {
    try {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', '');
        textarea.style.cssText = 'position:absolute;left:-9999px;top:0;';
        document.body.appendChild(textarea);

        const isIOS = /ipad|iphone/i.test(navigator.userAgent);
        if (isIOS) {
            const range = document.createRange();
            range.selectNodeContents(textarea);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            textarea.setSelectionRange(0, 999999);
        } else {
            textarea.focus();
            textarea.select();
        }

        const ok = document.execCommand('copy');
        document.body.removeChild(textarea);
        if (isIOS) window.getSelection().removeAllRanges();
        return ok;
    } catch (_) {
        return false;
    }
}

function onCopySuccess() {
    const templateType = templateSelect.value;
    const msg = templateType === 'raw' ? '📋 Batch perfectly copied for AI Agent!' : '📋 Prompt successfully copied to clipboard!';
    showToast(msg);

    document.querySelectorAll('.copy-trigger').forEach(btn => {
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
            Copied!
        `;
        btn.style.background = 'linear-gradient(135deg, var(--accent-green) 0%, #059669 100%)';
        btn.style.boxShadow = '0 4px 12px rgba(16, 185, 129, 0.3)';
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.style.background = '';
            btn.style.boxShadow = '';
        }, 2000);
    });
}

function showToast(message, duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'toast';

    let icon = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
    if (message.includes('🔄') || message.toLowerCase().includes('fetching')) {
        icon = '<div class="spinner" style="width:16px;height:16px;border-width:2px;flex-shrink:0;"></div>';
        toast.style.borderLeftColor = 'var(--accent-blue)';
    } else if (message.includes('❌') || message.toLowerCase().includes('error') || message.toLowerCase().includes('failed') || message.includes('⚠️')) {
        icon = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';
        toast.style.borderLeftColor = 'var(--accent-red)';
    }

    toast.innerHTML = `${icon} ${message}`;
    container.appendChild(toast);

    const removeToast = () => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    };

    if (duration > 0) {
        setTimeout(removeToast, duration);
    }

    return { toast, remove: removeToast };
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ─── CRM Tab System ───────────────────────────────────────────────────────────
function initTabSystem() {
    const tabs = document.querySelectorAll('.tab-button');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-target');

            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.add('hidden');
            });
            document.getElementById(target).classList.remove('hidden');

            if (target === 'tracker-view') {
                fetchTrackerData();
            }

            safeStorage.setItem('crm_active_tab', target);
            updateSelectionUI();
        });
    });
}

async function fetchAppliedUrlsOnly() {
    let data = null;
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (isLocal) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            const res = await fetch((API_BASE || '') + '/api/tracker', { signal: controller.signal });
            clearTimeout(timeoutId);
            if (res.ok) data = await res.json();
        } catch (_) {}
    }
    if (!data) {
        try {
            let csvRes = await fetch('./data/crm_applications.csv');
            if (!csvRes.ok) csvRes = await fetch('data/crm_applications.csv');
            if (csvRes.ok) {
                const text = await csvRes.text();
                data = parseCSV(text);
            }
        } catch (_) {}
    }
    if (data && Array.isArray(data)) {
        state.appliedUrls = new Set(data.map(item => item.job_url).filter(Boolean));
        state.appliedKeys = new Set(data.map(item => {
            const comp = normalizeText(item.company);
            const pos = normalizeTitle(item.position);
            return comp && pos ? `${comp}|||${pos}` : null;
        }).filter(Boolean));
    }
}

async function fetchTrackerData(silent = false) {
    const tbody = document.getElementById('tracker-tbody');
    if (!silent && tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="loading-state">
                    <div class="spinner"></div>
                    <p>Loading application tracker...</p>
                </td>
            </tr>
        `;
    }

    let data = null;
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (isLocal) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            const response = await fetch((API_BASE || '') + '/api/tracker', { signal: controller.signal });
            clearTimeout(timeoutId);
            if (response.ok && (response.headers.get('content-type') || '').includes('application/json')) {
                data = await response.json();
            }
        } catch (_) {}
    }

    if (!data || data.error) {
        try {
            let csvRes = await fetch('./data/crm_applications.csv');
            if (!csvRes.ok) csvRes = await fetch('../data/crm_applications.csv');
            if (!csvRes.ok) csvRes = await fetch('data/crm_applications.csv');
            if (csvRes.ok) {
                const text = await csvRes.text();
                data = parseCSV(text);
            }
        } catch (e) {
            console.error('Failed to load static CRM csv:', e);
        }
    }

    if (!data) data = [];

    trackerState.allRecords = data;
    state.appliedUrls = new Set(data.map(item => item.job_url).filter(Boolean));
    state.appliedKeys = new Set(data.map(item => {
        const comp = normalizeText(item.company);
        const pos = normalizeTitle(item.position);
        return comp && pos ? `${comp}|||${pos}` : null;
    }).filter(Boolean));

    applyTrackerFilters();
}

function cleanLink(l) {
    if (!l) return '';
    const s = String(l).trim();
    const lower = s.toLowerCase();
    if (lower === '' || lower === 'n/a' || lower === 'null' || lower === 'undefined' || lower === '#') return '';
    return s;
}

let _trackerFilterDebounceTimer = null;
function applyTrackerFiltersDebounced() {
    clearTimeout(_trackerFilterDebounceTimer);
    _trackerFilterDebounceTimer = setTimeout(() => applyTrackerFilters(), 120);
}

function applyTrackerFilters() {
    let filtered = trackerState.allRecords;
    if (trackerState.filterStatus) {
        filtered = filtered.filter(item => {
            const cur = (item.status || item.notes || 'Applied').toLowerCase();
            return cur === trackerState.filterStatus.toLowerCase();
        });
    }
    if (trackerState.filterDate) {
        filtered = filtered.filter(item => item.date_applied === trackerState.filterDate);
    }
    if (trackerState.filterSearch) {
        filtered = filtered.filter(item => {
            const posMatch = (item.position || '').toLowerCase().includes(trackerState.filterSearch);
            const compMatch = (item.company || '').toLowerCase().includes(trackerState.filterSearch);
            const notesMatch = (item.notes || '').toLowerCase().includes(trackerState.filterSearch);
            return posMatch || compMatch || notesMatch;
        });
    }
    if (trackerState.showUnopenedOnly) {
        filtered = filtered.filter(item => {
            const jobUrl = cleanLink(item.job_url);
            const cvPath = cleanLink(item.cv_pdf_path);
            const hasJobUrl = jobUrl !== '';
            const hasCv = cvPath !== '';

            if (!hasJobUrl && !hasCv) return false;

            let isOpened = false;
            const clPath = cvPath ? cvPath.replace('_cv.pdf', '_cover.pdf') : '';

            if (hasJobUrl && trackerState.openedUrls.has(jobUrl)) {
                isOpened = true;
            }
            if (hasCv && (trackerState.openedUrls.has(cvPath) || trackerState.openedUrls.has(clPath))) {
                isOpened = true;
            }
            return !isOpened;
        });
    }
    renderTrackerTable(filtered);
    saveFilterState();
}

function getLocalDateString(d = new Date()) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function updateUnopenedCount() {
    const unopenedEl = document.getElementById('crm-unopened-links');
    if (!unopenedEl) return;

    let unopenedCount = 0;
    trackerState.allRecords.forEach(item => {
        const appliedDate = (item.date_applied || '').trim();
        if (trackerState.filterDate && appliedDate !== trackerState.filterDate) {
            return;
        }

        const jobUrl = cleanLink(item.job_url);
        const cvPath = cleanLink(item.cv_pdf_path);

        const hasJobUrl = jobUrl !== '';
        const hasCv = cvPath !== '';

        if (!hasJobUrl && !hasCv) return;

        let isOpened = false;
        const clPath = cvPath ? cvPath.replace('_cv.pdf', '_cover.pdf') : '';

        if (hasJobUrl && trackerState.openedUrls.has(jobUrl)) {
            isOpened = true;
        }
        if (hasCv && (trackerState.openedUrls.has(cvPath) || trackerState.openedUrls.has(clPath))) {
            isOpened = true;
        }

        if (!isOpened) {
            unopenedCount++;
        }
    });

    unopenedEl.textContent = unopenedCount;
}

window.markLinkOpened = function (href, evt) {
    if (!href) return;
    if (evt && evt.currentTarget) {
        evt.currentTarget.classList.add('opened-link');
    }
    trackerState.openedUrls.add(href);
    const cleaned = cleanLink(href);
    if (cleaned) trackerState.openedUrls.add(cleaned);
    safeStorage.setItem('crm_opened_urls', JSON.stringify(Array.from(trackerState.openedUrls)));
    updateUnopenedCount();
    applyTrackerFilters();
};

function updateTrackerHeaderIcons() {
    document.querySelectorAll('th.tracker-sortable').forEach(header => {
        const icon = header.querySelector('.tracker-sort-icon');
        if (!icon) return;
        if (header.dataset.trackerSort === trackerState.sortColumn) {
            icon.innerHTML = trackerState.sortDirection === 'asc' ? ' ▲' : ' ▼';
            header.classList.add('active-sort');
        } else {
            icon.innerHTML = '';
            header.classList.remove('active-sort');
        }
    });
}

function renderTrackerTable(data) {
    const tbody = document.getElementById('tracker-tbody');
    const totalAppsEl = document.getElementById('crm-total-apps');
    const visibleCountEl = document.getElementById('tracker-visible-count');

    updateTrackerHeaderIcons();

    if (data && data.length > 0) {
        const col = trackerState.sortColumn || 'date_applied';
        const dir = trackerState.sortDirection === 'asc' ? 1 : -1;

        data.sort((a, b) => {
            if (col === 'company') {
                const cmp = (a.company || '').localeCompare(b.company || '');
                if (cmp !== 0) return cmp * dir;
            } else if (col === 'position') {
                const cmp = (a.position || '').localeCompare(b.position || '');
                if (cmp !== 0) return cmp * dir;
            } else if (col === 'notes') {
                const noteA = (a.notes || '').trim();
                const noteB = (b.notes || '').trim();
                const hasA = noteA.length > 0 ? 1 : 0;
                const hasB = noteB.length > 0 ? 1 : 0;
                if (hasA !== hasB) return (hasB - hasA) * dir;
                const cmp = noteA.localeCompare(noteB);
                if (cmp !== 0) return cmp * dir;
            } else if (col === 'date_applied') {
                const dateA = String(a.date_applied || '').trim();
                const dateB = String(b.date_applied || '').trim();
                if (dateA !== dateB) {
                    return (dateA < dateB ? -1 : 1) * dir;
                }
            }

            // Default tie-breaker: strict LIFO by CSV insertion order (_csv_index)
            const idxA = typeof a._csv_index === 'number' ? a._csv_index : 0;
            const idxB = typeof b._csv_index === 'number' ? b._csv_index : 0;
            if (idxA !== idxB) {
                return (idxA < idxB ? -1 : 1) * dir;
            }
            return 0;
        });
    }

    if (!data || data.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <p>No tracked applications found. Use "Mark Applied" inside job details to start tracking.</p>
                </td>
            </tr>
        `;
        totalAppsEl.textContent = '0';
        visibleCountEl.textContent = '0';
        return;
    }

    tbody.innerHTML = '';
    data.forEach(item => {
        const tr = document.createElement('tr');

        const CRM_STATUSES = ['Applied', 'Interview', 'Offer', 'Rejected', 'Ghosted'];
        const currentStatus = item.status || item.notes || 'Applied';
        const normalised = CRM_STATUSES.find(s => s.toLowerCase() === currentStatus.toLowerCase()) || 'Applied';
        const statusColorClass = {
            Applied: 'status-applied', Interview: 'status-interview',
            Offer: 'status-offer', Rejected: 'status-rejected', Ghosted: 'status-ghosted'
        }[normalised] || 'status-applied';
        const statusHtml = `
            <select class="tracker-status-select ${statusColorClass}"
                    onchange="updateApplicationStatus('${escapeHtml(item.job_url || '')}', '${escapeHtml(item.company || '')}', '${escapeHtml(item.position || '')}', this.value, this)">
                ${CRM_STATUSES.map(s => `<option value="${s}"${s === normalised ? ' selected' : ''}>${s}</option>`).join('')}
            </select>
        `;

        const jobUrlClean = cleanLink(item.job_url);
        const cvPdfClean = cleanLink(item.cv_pdf_path);
        const clPdfClean = cvPdfClean ? cvPdfClean.replace('_cv.pdf', '_cover.pdf') : '';
        const isTitleOpened = Boolean(jobUrlClean && trackerState.openedUrls && trackerState.openedUrls.has(jobUrlClean));

        // Simplified Title Logic: Click opens CRM drawer with Job Description
        let titleHtml = '';
        const safeUrl = escapeHtml(item.job_url || '');
        const safeComp = escapeHtml(item.company || '');
        const safePos = escapeHtml(item.position || '');
        if (jobUrlClean) {
            titleHtml = `<a href="javascript:void(0)" onclick="openCrmDrawer('${safeUrl}', '${safeComp}', '${safePos}'); markLinkOpened('${safeUrl}', event)" class="job-title-link ${isTitleOpened ? 'opened-link' : ''}" title="View locally saved job description">${safePos}</a>`;
        } else {
            titleHtml = `<a href="javascript:void(0)" onclick="openCrmDrawer('${safeUrl}', '${safeComp}', '${safePos}')" class="job-title-link ${isTitleOpened ? 'opened-link' : ''}" title="View locally saved job description">${safePos}</a>`;
        }
        let artifactsHtml = '';
        if (cvPdfClean) {
            const isCvOpened = trackerState.openedUrls.has(cvPdfClean);
            const isClOpened = trackerState.openedUrls.has(clPdfClean);
            artifactsHtml += `
                <a href="/${escapeHtml(item.cv_pdf_path)}" target="_blank" onclick="markLinkOpened('${escapeHtml(item.cv_pdf_path)}', event)" class="btn-icon-link ${isCvOpened ? 'opened-link' : ''}" title="Open CV PDF" style="margin-right: 4px;">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8.5 7.5c0 .83-.67 1.5-1.5 1.5H9v2H7.5V7H10c.83 0 1.5.67 1.5 1.5v1zm5 2c0 .83-.67 1.5-1.5 1.5h-2.5V7H15c.83 0 1.5.67 1.5 1.5v3zm4-3H19v1h1.5V11H19v2h-1.5V7h3v1.5zM9 9.5h1v-1H9v1zm5.5 2h1v-3h-1v3z"/></svg>
                </a>
                <a href="/${escapeHtml(clPdfClean)}" target="_blank" onclick="markLinkOpened('${escapeHtml(clPdfClean)}', event)" class="btn-icon-link ${isClOpened ? 'opened-link' : ''}" title="Open Cover Letter PDF" style="margin-right: 4px;">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                </a>
            `;
        }

        const emailContact = item.email_contact || '';
        artifactsHtml += `
            <button class="btn-icon-link" onclick="triggerEmailForTracker('${safeComp}', '${safePos}', '${safeUrl}', '${escapeHtml(emailContact)}');" title="Compose Application / Follow-up Email with Gemini AI" style="margin-right: 4px; cursor: pointer;">
                <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
            </button>
        `;

        if (jobUrlClean && !jobUrlClean.toLowerCase().startsWith('mailto:')) {
            const isUrlOpened = trackerState.openedUrls.has(jobUrlClean);
            artifactsHtml += `
                <a href="${escapeHtml(item.job_url)}" target="_blank" onclick="markLinkOpened('${escapeHtml(item.job_url)}', event)" class="btn-link ${isUrlOpened ? 'opened-link' : ''}" title="Open Job Posting URL" style="margin-right: 4px;">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
                </a>
            `;
        }
        if (artifactsHtml === '') {
            artifactsHtml = '<span style="color: var(--text-muted)">N/A</span>';
        }
        artifactsHtml = `<div class="crm-artifact-actions">${artifactsHtml}</div>`;

        const deleteButtonHtml = `
            <button class="btn-icon-link delete-btn" onclick="deleteApplication('${escapeHtml(item.cv_pdf_path)}', '${escapeHtml(item.company)}', '${escapeHtml(item.position)}', '${escapeHtml(item.job_url || '')}')" title="Delete Application & Files" style="color: #EF4444; border-color: rgba(239, 68, 68, 0.25);">
                <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
            </button>
        `;

        tr.innerHTML = `
            <td class="col-title" style="font-weight: 600;">${titleHtml}</td>
            <td class="col-company">${escapeHtml(item.company || '')}</td>
            <td class="col-date">${escapeHtml(item.date_applied || '')}</td>
            <td class="col-status">${statusHtml}</td>
            <td class="col-actions col-artifacts">${artifactsHtml}</td>
            <td class="col-actions col-delete">${deleteButtonHtml}</td>
        `;

        tbody.appendChild(tr);
    });

    totalAppsEl.textContent = trackerState.allRecords ? trackerState.allRecords.length : 0;
    visibleCountEl.textContent = data.length;
    updateUnopenedCount();
}

window.applyJobFromDrawer = function (idx) {
    const job = state.allJobs.find(j => j._originalIndex === idx);
    if (!job) return;

    const payload = {
        company: job.company || 'Unknown',
        position: job.title || 'Unknown',
        status: 'applied',
        date_applied: getLocalDateString(),
        match_score: job.score || 0,
        ai_score: job.ai_score || '',
        source: job.portal || 'unknown',
        job_url: job.job_url || '',
        cv_pdf_path: '',
        notes: ''
    };

    fetch(API_BASE + '/api/applications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(res => res.json())
        .then(data => {
            if (data.error) throw new Error(data.error);
            showToast('✓ Application tracked successfully!');
            state.appliedUrls.add(job.job_url);
            const compNorm = normalizeText(job.company);
            const posNorm = normalizeTitle(job.title);
            if (compNorm && posNorm) state.appliedKeys.add(`${compNorm}|||${posNorm}`);
            // Refresh drawer to show Applied button
            renderDrawerDetails(job);
        })
        .catch(err => {
            showToast('❌ Failed to track application: ' + err.message);
        });
};

window.updateApplicationNotes = function (jobUrl, company, position, notes) {
    const base = (typeof API_BASE !== 'undefined' ? API_BASE : (window.API_BASE || ''));
    fetch(base + '/api/applications/notes', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_url: jobUrl, company, position, notes })
    })
        .then(async res => {
            let data = null;
            try { data = await res.json(); } catch (_) { if (res.ok) return { success: true }; }
            if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
            return data;
        })
        .catch(err => {
            showToast('❌ Failed to save note: ' + err.message);
        });
};


// CRM Status update
window.updateApplicationStatus = function (jobUrl, company, position, newStatus, selectEl) {
    const colorMap = {
        Applied: 'status-applied', Interview: 'status-interview',
        Offer: 'status-offer', Rejected: 'status-rejected', Ghosted: 'status-ghosted'
    };
    // Update visual immediately — no waiting for server
    if (selectEl) selectEl.className = 'tracker-status-select ' + (colorMap[newStatus] || 'status-applied');

    const base = (typeof API_BASE !== 'undefined' ? API_BASE : (window.API_BASE || ''));
    fetch(base + '/api/applications/notes', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_url: jobUrl, company, position, notes: newStatus, status: newStatus })
    })
    .then(async res => {
        let data = null;
        try {
            data = await res.json();
        } catch (_) {
            if (res.ok) return { success: true };
            throw new Error(`Server returned HTTP ${res.status}`);
        }
        if (!res.ok) {
            throw new Error((data && data.error) ? data.error : `HTTP ${res.status}`);
        }
        return data;
    })
    .then(data => {
        showToast('✓ Status: ' + newStatus);
        // Update in-memory record so re-render is correct without refetch
        if (typeof trackerState !== 'undefined' && trackerState.allRecords) {
            const rec = trackerState.allRecords.find(r =>
                (jobUrl && r.job_url === jobUrl) ||
                (company && position && r.company === company && r.position === position)
            );
            if (rec) { rec.status = newStatus; rec.notes = newStatus; }
        }
    })
    .catch(err => {
        console.error('Status update error:', err);
        showToast('⚠️ Status save failed: ' + err.message);
    });
};

window.deleteApplication = function (cvPdfPath, company, position, jobUrl) {
    if (!confirm(`Delete application for "${position}" at "${company}"?\n\nThis will also delete CV and cover letter PDF files if they exist.`)) return;

    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const compNorm = normalizeText(company);
    const posNorm = normalizeTitle(position);

    // Immediately update local in-memory state so it disappears instantly
    if (jobUrl) state.dismissedUrls.add(jobUrl);
    if (compNorm && posNorm) state.dismissedKeys.add(`${compNorm}|||${posNorm}`);
    if (jobUrl) state.appliedUrls.delete(jobUrl);
    if (compNorm && posNorm) state.appliedKeys.delete(`${compNorm}|||${posNorm}`);

    if (typeof trackerState !== 'undefined' && trackerState.allRecords) {
        trackerState.allRecords = trackerState.allRecords.filter(item => {
            if (jobUrl && item.job_url && item.job_url === jobUrl) return false;
            if (compNorm && posNorm && normalizeText(item.company) === compNorm && normalizeTitle(item.position) === posNorm) return false;
            return true;
        });
        applyTrackerFilters();
    }
    applyFiltersAndRender();

    if (!isLocal) {
        showToast('⚠️ GitHub Pages is read-only. Job hidden from current view. Run local server to sync disk & Git.', 7000);
        return;
    }

    const base = (typeof API_BASE !== 'undefined' ? API_BASE : (window.API_BASE || ''));
    fetch(base + '/api/applications', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv_pdf_path: cvPdfPath, company, position, job_url: jobUrl })
    })
    .then(async res => {
        let data = null;
        try {
            data = await res.json();
        } catch (_) {
            if (res.ok) return { success: true };
            throw new Error(`Server returned HTTP ${res.status}`);
        }
        if (!res.ok) {
            throw new Error((data && data.error) ? data.error : `HTTP ${res.status}`);
        }
        return data;
    })
    .then(data => {
        showToast('✓ Application deleted & removed from CRM');
        fetchTrackerData(true);
    })
    .catch(err => {
        console.error('Delete application error:', err);
        showToast('❌ Failed to delete: ' + (err.message.includes('Failed to fetch') ? 'Cannot connect to backend server. Make sure server is running on port 8000.' : err.message));
    });
};

function fetchDismissedJobs() {
    // Dismissed jobs are directly purged from CSV datasets; no client-side ghost filtering needed.
}

window.dismissJob = function (jobUrl, company, position) {
    if (!confirm(`Delete "${position}" at "${company}" permanently from your list?`)) return;

    // Remove from in-memory list immediately
    const compNorm = normalizeText(company);
    const posNorm = normalizeTitle(position);

    state.allJobs = state.allJobs.filter(j => {
        if (jobUrl && j.job_url === jobUrl) return false;
        if (compNorm && posNorm && normalizeText(j.company) === compNorm && normalizeTitle(j.title) === posNorm) return false;
        return true;
    });

    applyFiltersAndRender();

    fetch(API_BASE + '/api/dismissed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_url: jobUrl, company, position })
    })
        .then(res => res.json())
        .then(data => {
            showToast('✓ Job permanently deleted from dataset');
        })
        .catch(err => {
            showToast('❌ Failed to delete job: ' + err.message);
        });
};

// ─── Filter State Persistence ─────────────────────────────────────────────────
function saveFilterState() {
    try {
        const filterSnapshot = {
            search: state.filters.search,
            company: state.filters.company,
            location: state.filters.location,
            dateRange: state.filters.dateRange,
            customDate: state.filters.customDate,
            portals: state.filters.portals,
            trackerFilterStatus: trackerState.filterStatus,
            trackerFilterDate: trackerState.filterDate,
            trackerFilterSearch: trackerState.filterSearch,
            trackerShowUnopenedOnly: trackerState.showUnopenedOnly
        };
        safeStorage.setItem('karriere_filter_state', JSON.stringify(filterSnapshot));
    } catch (e) {
        console.warn('Could not save filter state:', e);
    }
}

function restoreFilterState() {
    try {
        const saved = safeStorage.getItem('karriere_filter_state');
        if (!saved) return;
        const snap = JSON.parse(saved);

        // Restore job filters
        if (snap.search !== undefined) {
            state.filters.search = snap.search;
            if (searchInput) searchInput.value = snap.search;
        }
        if (snap.company !== undefined) {
            state.filters.company = snap.company;
            // companySelector options aren't loaded yet — will be set after populateCompanyFilter
        }
        if (snap.location !== undefined) {
            state.filters.location = snap.location;
            if (locationInput) locationInput.value = snap.location;
        }
        if (snap.dateRange !== undefined) {
            state.filters.dateRange = snap.dateRange;
            if (dateSelector) dateSelector.value = snap.dateRange;
        }
        if (snap.customDate !== undefined) {
            state.filters.customDate = snap.customDate;
            if (customDateInput) customDateInput.value = snap.customDate;
        }
        if (snap.portals) {
            state.filters.portals = { ...state.filters.portals, ...snap.portals };
            if (linkedinCheckbox) linkedinCheckbox.checked = snap.portals.linkedin !== false;
            if (indeedCheckbox) indeedCheckbox.checked = snap.portals.indeed !== false;
            if (baCheckbox) baCheckbox.checked = snap.portals.ba !== false;
        }

        // Restore tracker filters
        if (snap.trackerFilterStatus !== undefined) {
            trackerState.filterStatus = snap.trackerFilterStatus;
            const el = document.getElementById('tracker-filter-status');
            if (el) el.value = snap.trackerFilterStatus;
        }
        if (snap.trackerFilterDate !== undefined) {
            trackerState.filterDate = snap.trackerFilterDate;
            const el = document.getElementById('tracker-filter-date');
            if (el) el.value = snap.trackerFilterDate;
        }
        if (snap.trackerFilterSearch !== undefined) {
            trackerState.filterSearch = snap.trackerFilterSearch;
            const el = document.getElementById('tracker-filter-search');
            if (el) el.value = snap.trackerFilterSearch;
        }
        if (snap.trackerShowUnopenedOnly !== undefined) {
            trackerState.showUnopenedOnly = snap.trackerShowUnopenedOnly;
            const el = document.getElementById('tracker-filter-unopened');
            if (el) el.checked = snap.trackerShowUnopenedOnly;
        }
    } catch (e) {
        console.warn('Could not restore filter state:', e);
    }
}
// ─────────────────────────────────────────────────────────────────────────────

// Run Scraper Button Handler & Status Polling
function showToastNotification(message, isError = false, allowHtml = false) {
    let toast = document.getElementById('pipeline-toast-notification');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'pipeline-toast-notification';
        toast.style.cssText = 'position: fixed; bottom: 24px; right: 24px; z-index: 9999; padding: 12px 20px; border-radius: 8px; font-weight: 500; font-size: 0.88rem; box-shadow: 0 10px 25px rgba(0,0,0,0.4); transition: all 0.3s ease; display: flex; align-items: center; gap: 10px;';
        document.body.appendChild(toast);
    }
    toast.style.background = isError ? '#450a0a' : '#0f172a';
    toast.style.color = isError ? '#fca5a5' : '#38bdf8';
    toast.style.border = isError ? '1px solid #ef4444' : '1px solid #38bdf8';
    const content = allowHtml ? message : escapeHtml(message);
    toast.innerHTML = isError ? `⚠️ <span>${content}</span>` : `ℹ️ <span>${content}</span>`;
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
    }, 7000);
}

document.addEventListener('DOMContentLoaded', () => {
        // Sync from GitHub handler
    const btnSync = document.getElementById('btn-sync-github');
    const btnSyncText = document.getElementById('btn-sync-text');
    if (btnSync) {
        btnSync.addEventListener('click', async () => {
            btnSync.disabled = true;
            if (btnSyncText) btnSyncText.textContent = 'Pulling...';
            try {
                const res = await fetch((API_BASE || '') + '/api/sync');
                const data = await res.json();
                if (data.success) {
                    datasetCache.clear();
                    showScraperToast('✓ ' + (data.message || 'Synced with GitHub!'));
                    await fetchCSVFiles();
                } else {
                    showScraperToast('⚠️ ' + (data.error || 'Sync returned notice'));
                }
            } catch (err) {
                showScraperToast('⚠️ Sync error: ' + err.message);
            } finally {
                btnSync.disabled = false;
                if (btnSyncText) btnSyncText.textContent = 'Sync Git';
            }
        });
    }

    const btnScraper = document.getElementById('btn-trigger-scraper');
    const selectPortal = document.getElementById('scraper-portal-select');
    const selectDays = document.getElementById('scraper-days-select');
    const btnText = document.getElementById('btn-trigger-scraper-text');

    if (btnScraper && selectPortal) {
        let scraperPollTimer = null;

        btnScraper.addEventListener('click', async () => {
            const portal = selectPortal.value || 'all';
            const days = selectDays ? parseInt(selectDays.value, 10) : 1;
            btnScraper.disabled = true;
            if (btnText) btnText.textContent = `Scraping (${portal.toUpperCase()}, ${days}d)...`;

            const isStaticPages = window.location.hostname.endsWith('github.io');

            // If running on GitHub Pages (static hosting without local backend)
            if (isStaticPages) {
                showToastNotification('ℹ️ Cloud scraping is managed via GitHub Actions. Opening GitHub Actions...', false, true);
                window.open('https://github.com/Toya62/karriere-pipeline/actions', '_blank');
                setTimeout(() => {
                    btnScraper.disabled = false;
                    if (btnText) btnText.textContent = 'Run Scraper';
                }, 3000);
                return;
            }

            fetch((window.API_BASE || API_BASE || '') + '/api/run-scraper', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ portal, days })
            })
                .then(async res => {
                    const contentType = res.headers.get('content-type') || '';
                    if (!contentType.includes('application/json')) {
                        const text = await res.text();
                        throw new Error(`Server returned non-JSON response (HTTP ${res.status}). Server may be restarting or updating.`);
                    }
                    if (!res.ok) {
                        const errData = await res.json().catch(() => ({}));
                        throw new Error(errData.error || `HTTP ${res.status}`);
                    }
                    return res.json();
                })
                .then(data => {
                    if (data.success) {
                        if (data.mode === 'github_actions') {
                            showToastNotification(
                                `🚀 GitHub Actions scraper workflow triggered for ${portal.toUpperCase()} (${days}d)! <a href="${data.actions_url}" target="_blank" style="color: #60a5fa; text-decoration: underline; font-weight: 600;">View Live Logs on GitHub</a>`,
                                false,
                                true
                            );
                            setTimeout(() => {
                                btnScraper.disabled = false;
                                if (btnText) btnText.textContent = 'Run Scraper';
                            }, 5000);
                        } else {
                            showToastNotification(`⚡ Scraper started on server for ${portal.toUpperCase()} (${days}d)! Live results will auto-refresh...`, false);

                            if (scraperPollTimer) clearInterval(scraperPollTimer);
                            scraperPollTimer = setInterval(() => {
                                fetch((window.API_BASE || API_BASE || '') + '/api/scraper-status')
                                    .then(r => r.json())
                                    .then(statusData => {
                                        if (!statusData.running) {
                                            clearInterval(scraperPollTimer);
                                            scraperPollTimer = null;
                                            btnScraper.disabled = false;
                                            if (btnText) btnText.textContent = 'Run Scraper';
                                            showToastNotification('✅ Scraping completed! Reloading fresh jobs...', false);
                                            fetchJobsData();
                                        }
                                    })
                                    .catch(() => { });
                            }, 3000);
                        }
                    } else {
                        btnScraper.disabled = false;
                        if (btnText) btnText.textContent = 'Run Scraper';
                        showToastNotification(data.error || 'Cannot start scraper', true);
                    }
                })
                .catch(err => {
                    btnScraper.disabled = false;
                    if (btnText) btnText.textContent = 'Run Scraper';
                    showToastNotification(`Error triggering scraper: ${err.message}`, true);
                });
        });
    }

    // ── Scraper Log Modal Controller ──
    const btnViewLogs = document.getElementById('btn-view-logs');
    const logModal = document.getElementById('log-modal-backdrop');
    const btnCloseLogs = document.getElementById('btn-close-logs');
    const btnRefreshLogs = document.getElementById('btn-refresh-logs');
    const logViewer = document.getElementById('scraper-log-viewer');
    const logStatusBadge = document.getElementById('log-status-badge');
    let logPollTimer = null;

    async function fetchScraperLogs() {
        if (!logViewer) return;
        try {
            const res = await fetch((window.API_BASE || API_BASE || '') + '/api/scraper-logs');
            if (res.ok) {
                const data = await res.json();
                logViewer.textContent = data.logs || 'No log output recorded.';
                logViewer.scrollTop = logViewer.scrollHeight;
                if (logStatusBadge) {
                    logStatusBadge.textContent = 'Live (' + (data.total_lines || 0) + ' lines)';
                }
            } else {
                logViewer.textContent = 'Failed to load logs (HTTP ' + res.status + ').';
            }
        } catch (e) {
            logViewer.textContent = 'Error connecting to log endpoint: ' + e.message;
        }
    }

    if (btnViewLogs && logModal) {
        btnViewLogs.addEventListener('click', () => {
            logModal.style.display = 'flex';
            logModal.classList.remove('hidden');
            fetchScraperLogs();
            if (logPollTimer) clearInterval(logPollTimer);
            logPollTimer = setInterval(fetchScraperLogs, 3000);
        });

        if (btnCloseLogs) {
            btnCloseLogs.addEventListener('click', () => {
                logModal.style.display = 'none';
                logModal.classList.add('hidden');
                if (logPollTimer) {
                    clearInterval(logPollTimer);
                    logPollTimer = null;
                }
            });
        }

        if (btnRefreshLogs) {
            btnRefreshLogs.addEventListener('click', fetchScraperLogs);
        }

        logModal.addEventListener('click', (e) => {
            if (e.target === logModal) {
                logModal.style.display = 'none';
                logModal.classList.add('hidden');
                if (logPollTimer) {
                    clearInterval(logPollTimer);
                    logPollTimer = null;
                }
            }
        });
    }
});

// ═══════════════════════════════════════════════════════════════
// AI Email Application Composer Controller
// ═══════════════════════════════════════════════════════════════

let currentEmailJobContext = null;

window.detectJobEmail = function(job) {
    if (!job) return '';
    if (job.email_contact && String(job.email_contact).trim()) {
        return String(job.email_contact).trim();
    }
    const url = job.job_url || '';
    if (url.toLowerCase().startsWith('mailto:')) {
        return url.replace(/^mailto:/i, '').split('?')[0].trim();
    }
    if (url.includes('@') && !url.includes('/') && !url.includes('linkedin.com')) {
        return url.trim();
    }
    const desc = job.description || '';
    if (desc) {
        const matches = desc.match(/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/g);
        if (matches && matches.length > 0) {
            const ignored = ['example.com', 'test.com', 'sentry.io', 'domain.com', 'github.com', 'schema.org'];
            const valid = matches.filter(em => {
                const lower = em.toLowerCase();
                return !ignored.some(ig => lower.includes(ig)) && !lower.match(/\.(png|jpg|jpeg|gif|svg|webp)$/);
            });
            if (valid.length > 0) {
                const priority = valid.find(em => /bewerb|karriere|job|career|recruiting|apply|talent|hello|work|kontakt|contact/i.test(em));
                return priority || valid[0];
            }
        }
    }
    return '';
};

window.closeEmailModal = function() {
    const backdrop = document.getElementById('email-modal-backdrop');
    if (backdrop) backdrop.classList.add('hidden');
};

window.triggerEmailForJob = async function(idx) {
    const job = state.allJobs.find(j => j._originalIndex === idx);
    if (!job) return;
    const detectedEmail = detectJobEmail(job);
    openEmailComposer({
        company: job.company || '',
        position: job.title || '',
        description: job.description || '',
        job_url: job.job_url || '',
        email: detectedEmail
    });
};

window.triggerEmailForTracker = async function(company, position, job_url, email_contact) {
    // 1. Try to find matched job from state.allJobs for rich description
    const matched = (state.allJobs || []).find(j => 
        (job_url && j.job_url && j.job_url.trim() === job_url.trim()) ||
        (j.company && company && j.company.toLowerCase().trim() === company.toLowerCase().trim() &&
         j.title && position && (j.title.toLowerCase().includes(position.toLowerCase()) || position.toLowerCase().includes(j.title.toLowerCase())))
    );

    const desc = matched ? (matched.description || '') : '';
    let recEmail = email_contact || (matched ? detectJobEmail(matched) : '');

    openEmailComposer({
        company: company || (matched ? matched.company : ''),
        position: position || (matched ? matched.title : ''),
        description: desc,
        job_url: job_url || (matched ? matched.job_url : ''),
        email: recEmail
    });
};

window.openEmailComposer = async function(jobData) {
    currentEmailJobContext = jobData;
    const backdrop = document.getElementById('email-modal-backdrop');
    const toInput = document.getElementById('email-to-input');
    const subjectInput = document.getElementById('email-subject-input');
    const bodyInput = document.getElementById('email-body-input');
    const aiBadge = document.getElementById('email-ai-badge');
    const subtitleEl = document.getElementById('email-job-subtitle');
    const attachmentsList = document.getElementById('email-attachments-list');
    
    if (!backdrop) return;
    backdrop.classList.remove('hidden');

    let initialEmail = jobData.email || '';
    if (!initialEmail) {
        if (jobData.job_url && jobData.job_url.toLowerCase().startsWith('mailto:')) {
            initialEmail = jobData.job_url.replace(/^mailto:/i, '').split('?')[0].trim();
        } else if (jobData.description) {
            const m = jobData.description.match(/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/);
            if (m) initialEmail = m[0];
        }
    }

    toInput.value = initialEmail;
    if (subtitleEl) {
        subtitleEl.textContent = `${jobData.company || 'Company'} — ${jobData.position || 'Position'}`;
    }
    subjectInput.value = `Generating tailored subject for ${jobData.company || 'Job'}...`;
    bodyInput.value = `Analyzing full job description and requirements with Gemini AI...\n\nTarget: ${jobData.company || ''} – ${jobData.position || ''}\nCrafting high-converting application email matching the candidate's verified profile.\nPlease wait a moment...`;
    if (aiBadge) aiBadge.style.display = 'none';
    if (attachmentsList) attachmentsList.innerHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">Searching compiled applications in repository...</span>';

    try {
        const resp = await fetch((API_BASE || '') + '/api/generate-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                company: jobData.company,
                position: jobData.position,
                description: jobData.description,
                job_url: jobData.job_url,
                email: initialEmail
            })
        });
        const data = await resp.json();
        if (data.success) {
            toInput.value = data.recipient || toInput.value;
            subjectInput.value = data.subject || '';
            bodyInput.value = data.body || '';
            if (aiBadge) {
                aiBadge.style.display = data.ai_generated ? 'inline-block' : 'none';
                if (data.description_length > 0) {
                    aiBadge.title = `Trained on ${data.description_length.toLocaleString()} characters of job description & requirements`;
                }
            }
            if (subtitleEl && data.description_length > 0) {
                subtitleEl.textContent = `${jobData.company || data.company} — ${jobData.position || data.position} (${data.description_length.toLocaleString()} chars description analyzed)`;
            }
            
            if (attachmentsList) {
                if (data.attachments && data.attachments.length > 0) {
                    attachmentsList.innerHTML = data.attachments.map(att => `
                        <a href="/${att.path}" target="_blank" class="attachment-pill" title="View ${att.name}">
                            <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                            ${att.name}
                        </a>
                    `).join('');
                } else {
                    attachmentsList.innerHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">No pre-compiled PDF found in applications/. Run generation for this job to attach PDFs.</span>';
                }
            }
        } else {
            subjectInput.value = `Bewerbung als ${jobData.position || 'Software Engineer'} – Candidate Name`;
            bodyInput.value = `Sehr geehrte Damen und Herren,\n\nhiermit bewerbe ich mich auf die Position als ${jobData.position} bei ${jobData.company}.\n\nMit freundlichen Grüßen,\nCandidate Name`;
        }
    } catch (e) {
        console.error('Failed to generate email draft:', e);
        subjectInput.value = `Bewerbung als ${jobData.position || 'Software Engineer'} – Candidate Name`;
    }
};

window.regenerateEmailDraft = function() {
    if (currentEmailJobContext) {
        openEmailComposer(currentEmailJobContext);
    }
};

window.launchMailto = function() {
    const to = document.getElementById('email-to-input').value.trim();
    const subject = document.getElementById('email-subject-input').value.trim();
    const body = document.getElementById('email-body-input').value.trim();

    const mailtoUrl = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.location.href = mailtoUrl;
};

window.copyEmailContent = function(mode) {
    const to = document.getElementById('email-to-input').value.trim();
    const subject = document.getElementById('email-subject-input').value.trim();
    const body = document.getElementById('email-body-input').value.trim();

    let textToCopy = '';
    if (mode === 'both') {
        textToCopy = `To: ${to}\nSubject: ${subject}\n\n${body}`;
    } else if (mode === 'subject') {
        textToCopy = subject;
    } else {
        textToCopy = body;
    }

    navigator.clipboard.writeText(textToCopy).then(() => {
        showToast('✓ Email content copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy to clipboard:', err);
    });
};

// Close modal on Escape key or backdrop click
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const backdrop = document.getElementById('email-modal-backdrop');
        if (backdrop && !backdrop.classList.contains('hidden')) {
            closeEmailModal();
        }
    }
});
document.addEventListener('click', (e) => {
    const backdrop = document.getElementById('email-modal-backdrop');
    if (e.target === backdrop) {
        closeEmailModal();
    }
});

window.openCrmDrawer = async function(jobUrl, company, position) {
    const drawer = document.getElementById('job-drawer');
    const drawerOverlay = document.getElementById('drawer-overlay');
    const drawerBody = document.getElementById('drawer-job-details');
    if (!drawer || !drawerOverlay || !drawerBody) return;

    drawer.classList.add('open');
    drawerOverlay.classList.add('open');

    let linkHtml = '';
    if (jobUrl && !jobUrl.toLowerCase().startsWith('mailto:')) {
        linkHtml = `
            <a href="${escapeHtml(jobUrl)}" target="_blank" class="btn-secondary" style="display: inline-flex; align-items: center; gap: 8px; margin-bottom: 20px; text-decoration: none;">
                <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
                Open Original Posting (Web)
            </a>`;
    } else if (jobUrl && jobUrl.toLowerCase().startsWith('mailto:')) {
        const emailAddr = jobUrl.replace(/^mailto:/i, '').split('?')[0].trim();
        linkHtml = `
            <a href="${escapeHtml(jobUrl)}" class="btn-secondary" style="display: inline-flex; align-items: center; gap: 8px; margin-bottom: 20px; text-decoration: none;">
                <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                Send Application Email (${escapeHtml(emailAddr)})
            </a>`;
    }

    drawerBody.innerHTML = `
        <div style="padding: 20px; font-family: var(--font-sans);">
            <h3 style="margin-bottom: 8px; color: var(--text-primary); font-size: 1.4rem;">${escapeHtml(position)}</h3>
            <div style="color: var(--text-secondary); margin-bottom: 20px; font-weight: 500;">
                <svg viewBox="0 0 24 24" width="16" height="16" style="vertical-align: text-bottom; margin-right: 4px;"><path fill="currentColor" d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/></svg>
                ${escapeHtml(company)}
            </div>
            ${linkHtml}
            <button class="btn-primary" style="display: inline-flex; align-items: center; gap: 8px; margin-bottom: 20px; padding: 9px 16px; background: linear-gradient(135deg, #0284c7, #0369a1); border: none; font-weight: 500; cursor: pointer;" onclick="triggerEmailForTracker('${escapeHtml(company)}', '${escapeHtml(position)}', '${escapeHtml(jobUrl)}', '')">
                <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                AI Application Email Composer
            </button>
            
            <div style="border-top: 1px solid var(--border-color); padding-top: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h4 style="margin: 0; color: var(--text-primary);">Locally Saved Description</h4>
                </div>
                <div id="crm-drawer-desc" style="background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; font-size: 0.9rem; line-height: 1.6; color: var(--text-secondary); white-space: pre-wrap; max-height: 480px; overflow-y: auto;">
                    <div class="spinner" style="margin: 20px auto;"></div>
                </div>
            </div>
        </div>
    `;

    try {
        const queryParams = new URLSearchParams();
        if (jobUrl) queryParams.set('urls', jobUrl);
        if (company) queryParams.set('company', company);
        if (position) queryParams.set('position', position);

        const res = await fetch((window.API_BASE || '') + `/api/job-descriptions?${queryParams.toString()}`);
        if (res.ok) {
            const map = await res.json();
            const desc = (jobUrl && map[jobUrl]) || map['_found_by_comp_pos'] || Object.values(map)[0];
            const descEl = document.getElementById('crm-drawer-desc');
            if (desc) {
                descEl.innerHTML = escapeHtml(desc);
            } else {
                descEl.innerHTML = '<em>No local description found in database.</em>';
            }
        }
    } catch (e) {
        document.getElementById('crm-drawer-desc').innerHTML = '<em>Failed to load local description.</em>';
    }
};

