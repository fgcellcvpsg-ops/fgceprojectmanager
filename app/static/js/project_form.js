// static/js/project_form.js
// Auto-fill client symbol, duplicate checks, and progress population.

(function () {
  function $(id) { return document.getElementById(id); }

  const clientSelect = $('client_id');
  const symbolInput = $('symbol');
  const poInput = $('po_number');
  const nameInput = $('name');
  const statusSelect = $('status');
  const progressSelect = $('progress');
  const ownerSelect = $('owners');

  const formEl = $('projectForm');

  // Parse Existing Projects
  let EXISTING = [];
  if (window.EXISTING_PROJECTS) {
     EXISTING = window.EXISTING_PROJECTS;
  } else if (formEl && formEl.dataset.existingProjects) {
     try {
         EXISTING = JSON.parse(formEl.dataset.existingProjects);
     } catch(e) { console.error('Error parsing existing projects data', e); }
  }

  // Parse Init
  let INIT = window.PROJECT_INIT || {};
  if (!window.PROJECT_INIT && formEl) {
      INIT = {
          mode: formEl.dataset.mode || 'add',
          initialProgress: formEl.dataset.initialProgress || '0',
          projectId: formEl.dataset.projectId || null
      };
  }
  
  // Store the initial PO Number value to check against later
  const initialPoValue = poInput ? poInput.value : '';
  const initialNameValue = nameInput ? nameInput.value : '';

  function normalize(s) {
    return (s || '').toString().trim().toLowerCase();
  }

  // Expose updateSymbolAlways globally so inline script can call it safely
  window.updateSymbolAlways = function () {
    if (!clientSelect || !symbolInput) return;
    const opt = clientSelect.options[clientSelect.selectedIndex];
    const clientSymbol = opt && opt.dataset ? (opt.dataset.symbol || '') : '';
    symbolInput.value = clientSymbol;
  };

  if (clientSelect) {
    clientSelect.addEventListener('change', window.updateSymbolAlways);
    // If options are populated later, you may need to call updateSymbolAlways again after injection.
    window.updateSymbolAlways();
  }

  // --- Start FGC/PEI Project Type Logic ---
  const typeFGC = $('typeFGC');
  const typePEI = $('typePEI');
  
  let poWarned = false; // Flag to track if user has been warned about changing PO

  function updateProjectType() {
    if (!typeFGC || !typePEI || !poInput) return;
    
    if (typePEI.checked) {
      // PEI Project:
      // User request: Default PO Number to "PEI"
      // "nếu dựu án thuộc pei thì mã duuựu án mậc định là PEI"
      
      // If it's already "PEI" or empty, set to "PEI". 
      // If user typed something else, maybe keep it?
      // But for consistency with "default is PEI", let's force it if it's currently empty or was cleared.
      if (!poInput.value || poInput.value === '') {
          poInput.value = 'PEI';
      }
      
      poInput.readOnly = false; // Allow editing if they want to append something
      poInput.disabled = false;
      poInput.required = false;
      poInput.removeAttribute('pattern'); // Remove 8-digit requirement
      poInput.removeAttribute('maxlength'); // Allow longer text if needed (or keep it if PEI should be short?)
      // Let's remove maxlength to be safe, or set it to something reasonable like 20.
      poInput.setAttribute('maxlength', '50'); 
      
      poInput.placeholder = typePEI.dataset.placeholder || 'PEI';
      poInput.classList.remove('bg-light'); // Editable
      
    } else if (typeFGC.checked) {
      // FGC Project:
      // Unlock PO Number for editing
      poInput.readOnly = false;
      poInput.disabled = false;
      poInput.required = true;
      poInput.setAttribute('pattern', '\\d{8}'); // Enforce 8 digits
      poInput.setAttribute('maxlength', '8');
      
      poInput.placeholder = typeFGC.dataset.placeholder || '8 chữ số, ví dụ: 12345678';
      poInput.classList.remove('bg-light');
      
      // User request: Restore existing value if available (only if it was an FGC number)
      // If the original value was an FGC number (8 digits), restore it.
      // If it was PEI or empty, leave it empty.
      const isOriginalFGC = /^\d{8}$/.test(initialPoValue);
      if (isOriginalFGC) {
          poInput.value = initialPoValue;
      } else {
          // If original was NOT FGC (e.g. PEI or new), then clear/keep empty
          poInput.value = '';
      }
      
    } else {
        // Neither checked
        poInput.readOnly = false;
        poInput.disabled = false;
        poInput.required = true;
        poInput.classList.remove('bg-light');
    }
  }

  // Warning logic when user attempts to change Project Number
  function handlePoInput(e) {
      if (!poInput.value && !poWarned) {
          // If value becomes empty (deleted), or maybe we should check on first edit?
          // User said: "khi bạn xóa thì sẽ hiện thông báo"
          // Let's warn when they try to change it if it had a value.
          // But 'input' fires AFTER change.
      }
  }
  
  // Better approach: intercept keydown
  function handlePoKeydown(e) {
      // Allow navigation keys without warning
      if (['ArrowLeft', 'ArrowRight', 'Tab', 'Enter', 'Copy', 'Paste'].includes(e.key) || e.ctrlKey || e.metaKey) return;
      
      // Warn ONLY if:
      // 1. We are in EDIT mode
      // 2. The field originally had a value (it's an existing number)
      // 3. User hasn't been warned yet
      if (INIT.mode === 'edit' && initialPoValue && !poWarned) {
          const formEl = $('projectForm');
          const msg = (formEl && formEl.dataset.msgConfirmChangePo) ? formEl.dataset.msgConfirmChangePo : "Bạn đang thay đổi Project Number, bạn có muốn tiếp tục không?";
          const confirmChange = confirm(msg);
          if (!confirmChange) {
              e.preventDefault();
              return;
          }
          poWarned = true;
      }
  }
  
  // Also catch cut/paste or other input methods?
  // 'beforeinput' is good but maybe simple keydown is enough for "deletion/typing".
  // Actually, if they select all and delete, keydown 'Delete'/'Backspace' triggers.

  if (typeFGC && typePEI) {
    typeFGC.addEventListener('change', updateProjectType);
    typePEI.addEventListener('change', updateProjectType);
    // Initialize state
    updateProjectType();
  }
  
  if (poInput) {
      poInput.addEventListener('keydown', handlePoKeydown);
      // Reset warning flag if form is reset? Or not needed.
  }
  // --- End FGC/PEI Project Type Logic ---

  function isPoDuplicateForClient(clientId, poValue, ownerId) {
    if (!poValue) return false;
    const poNorm = normalize(poValue);
    const currentPid = INIT.projectId ? String(INIT.projectId) : null;

    return EXISTING.some(p => {
      // Exclude current project from check (for edit mode)
      if (currentPid && String(p.id) === currentPid) return false;

      return String(p.client_id) === String(clientId) &&
             normalize(p.po_number) === poNorm &&
             (ownerId ? String(p.owner_id) === String(ownerId) : true);
    });
  }

  function handlePoBlur() {
    if (!poInput) return;
    const clientId = clientSelect ? clientSelect.value : null;
    const ownerId = (ownerSelect && ownerSelect.multiple)
      ? Array.from(ownerSelect.selectedOptions).map(o => o.value)
      : (ownerSelect ? ownerSelect.value : null);
    const poVal = poInput.value;
    if (!clientId) return;
    if (isPoDuplicateForClient(clientId, poVal, ownerId)) {
      const formEl = $('projectForm');
      const msg = (formEl && formEl.dataset.msgPoExists) ? formEl.dataset.msgPoExists : 'Project number này đã tồn tại cho client đã chọn (và người phụ trách nếu có). Vui lòng nhập số khác.';
      alert(msg);
      poInput.focus();
      poInput.select();
    }
  }
  if (poInput) poInput.addEventListener('blur', handlePoBlur);

  function isNameDuplicate(nameVal) {
    if (!nameVal) return false;
    // Don't check against self in edit mode if name hasn't changed (but handleNameBlur handles the 'changed' check)
    // However, EXISTING includes current project?
    // Usually EXISTING_PROJECTS in template excludes current project or we filter by ID.
    // Let's assume EXISTING_PROJECTS might include current.
    
    const nameNorm = normalize(nameVal);
    
    // Filter out current project if we know its ID? 
    // INIT.projectId could be useful. 
    // But for now, if name hasn't changed, we shouldn't be here (handleNameBlur check).
    
    return EXISTING.some(p => {
        // If we have current project ID, exclude it
        if (INIT.mode === 'edit' && INIT.projectId && String(p.id) === String(INIT.projectId)) {
            return false;
        }
        return normalize(p.name) === nameNorm;
    });
  }

  function handleNameBlur() {
    if (!nameInput) return;
    let rawVal = nameInput.value;
    if (!rawVal) return; // Nếu xóa hết thì thôi (hoặc xử lý required riêng)
    
    // FIX: Nếu giá trị chưa thay đổi so với ban đầu (người dùng chỉ click vào xem rồi click ra), thì không làm gì cả.
    if (INIT.mode === 'edit' && initialNameValue && rawVal === initialNameValue) {
        return;
    }
    
    let nameVal = rawVal;
    
    // Auto-format to Title Case (Python-like title() behavior)
    // Cải thiện Regex để hỗ trợ tiếng Việt (Unicode)
    try {
        // Sử dụng \p{L} để bắt tất cả ký tự chữ cái Unicode (bao gồm tiếng Việt)
        nameVal = nameVal.toLowerCase().replace(/(?:^|[\s_])\p{L}/gu, function (match) {
            return match.toUpperCase();
        });
    } catch (e) {
        // Fallback cho trình duyệt cũ không hỗ trợ /u flag
        // Chỉ hỗ trợ cơ bản a-z
        nameVal = nameVal.toLowerCase().replace(/(?:^|[\s_])[a-z]/g, function (match) {
            return match.toUpperCase();
        });
    }
    
    // Update input if casing changed
    if (nameInput.value !== nameVal) {
        nameInput.value = nameVal;
    }

    // LOGIC CHANGE: Only check if name is DIFFERENT from initial name
    // "chỉ khi nào ta xóa tên dự án và nhập lại tên mới thì hiển thị thông báo bạn muốn thay đổi tên dự án"
    if (INIT.mode === 'edit' && initialNameValue && nameVal !== initialNameValue) {
         // User changed the name (and it's different even after formatting)
         // User changed the name
         const confirmChange = confirm("Bạn muốn thay đổi tên dự án?");
         if (!confirmChange) {
             nameInput.value = initialNameValue; // Revert
             return;
         }
         
         // Then check duplicate
         // "rồi so sánh nếu đặt tên mới giống tên đã trồn tại thì hiện thông báo"
         if (isNameDuplicate(nameVal)) {
             const ok = confirm('Tên dự án này đã tồn tại trước đó. Bạn có chắc muốn đặt tên dự án này không?');
             if (!ok) {
                 // Revert to initial or clear? 
                 // User said "hiện thông báo", implying if they say No, we revert/clear.
                 // Revert seems safer than clear.
                 nameInput.value = initialNameValue;
                 nameInput.focus();
             }
         }
    } else if (INIT.mode === 'add' || !initialNameValue) {
        // Add mode or empty initial: just check duplicate
        if (isNameDuplicate(nameVal)) {
             const ok = confirm('Tên dự án này đã tồn tại trước đó. Bạn có chắc muốn đặt tên dự án này không?');
             if (!ok) {
                 nameInput.value = '';
                 nameInput.focus();
             }
        }
    }
  }
  if (nameInput) nameInput.addEventListener('blur', handleNameBlur);

  function populateProgressByStatus(status, currentProgress) {
    if (!progressSelect) return;
    progressSelect.innerHTML = '';
    progressSelect.classList.remove('text-danger', 'fw-bold');

    // Add Placeholder Option
    const placeholder = document.createElement('option');
    placeholder.value = "";
    placeholder.textContent = "Hãy chọn tiến độ";
    placeholder.disabled = true;
    placeholder.selected = true; // Default to placeholder
    progressSelect.appendChild(placeholder);

    const addOption = (val) => {
      const opt = document.createElement('option');
      opt.value = String(val);
      opt.textContent = String(val) + '%';
      progressSelect.appendChild(opt);
      return opt;
    };

    if (status === 'New') {
      const opt = addOption(0);
      opt.selected = true;
      placeholder.selected = false;
    } else if (status === 'In Progress') {
      // Must choose from specific options: 30, 50, 75, 90
      // Default: Placeholder (force choice)
      [30, 50, 75, 90].forEach(addOption);
      // If currentProgress match, select it
      if (currentProgress && [30, 50, 75, 90].includes(Number(currentProgress))) {
          progressSelect.value = String(currentProgress);
          placeholder.selected = false;
      }
    } else if (status === 'Completed') {
      const opt = addOption(100);
      opt.selected = true;
      placeholder.selected = false;
    } else if (status === 'On Hold') {
      // Keep current progress
      // Add all options 0..100
      for (let i = 0; i <= 100; i += 5) {
          const opt = addOption(i);
          if (String(i) === String(currentProgress)) {
              opt.selected = true;
              placeholder.selected = false;
          }
      }
      // If currentProgress is not multiple of 5 (e.g. 33), add it?
      if (currentProgress && (currentProgress % 5 !== 0)) {
           const opt = addOption(currentProgress);
           opt.selected = true;
           placeholder.selected = false;
      }
    } else {
        // Other statuses (Pending, Canceled)
        for (let i = 0; i <= 100; i += 5) addOption(i);
        if (currentProgress) {
            progressSelect.value = String(currentProgress);
            if (progressSelect.value === String(currentProgress)) placeholder.selected = false;
        }
    }
  }

  if (statusSelect) {
    statusSelect.addEventListener('change', function() {
       populateProgressByStatus(this.value, progressSelect ? progressSelect.value : null);
    });
    
    // On load, if it's Edit mode
    if (INIT.mode === 'edit' || statusSelect.value) {
        const initialVal = INIT.initialProgress || (progressSelect ? progressSelect.value : null);
        populateProgressByStatus(statusSelect.value, initialVal);
    }
  }

  if (formEl) {
    formEl.addEventListener('submit', function (e) {
      // Auto-format Name on submit just in case
      if (nameInput && nameInput.value) {
          try {
             let n = nameInput.value.toLowerCase().replace(/(?:^|[\s_])\p{L}/gu, m => m.toUpperCase());
             nameInput.value = n;
          } catch (e) {
             let n = nameInput.value.toLowerCase().replace(/(?:^|[\s_])[a-z]/g, m => m.toUpperCase());
             nameInput.value = n;
          }
      }

      if (poInput && clientSelect) {
        const clientId = clientSelect.value;
        const ownerId = (ownerSelect && ownerSelect.multiple)
          ? Array.from(ownerSelect.selectedOptions).map(o => o.value)
          : (ownerSelect ? ownerSelect.value : null);
        const poVal = poInput.value;
        if (clientId && isPoDuplicateForClient(clientId, poVal, ownerId)) {
          e.preventDefault();
          alert('Project number đã tồn tại cho client này. Vui lòng nhập số khác trước khi lưu.');
          poInput.focus();
          return false;
        }
      }
    });
  }
})();
