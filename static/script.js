document.addEventListener('DOMContentLoaded', () => {
  // Initialize Theme Control
  initTheme();

  // Detect which page is loaded
  const dashboardUpload = document.getElementById('drag-drop-card');
  if (dashboardUpload) {
    initDashboard(dashboardUpload);
  }

  const viewerContainer = document.getElementById('chat-viewer-viewport');
  if (viewerContainer) {
    initViewer();
  }
});

/* ==========================================================================
   Theme Management (Light/Dark Mode)
   ========================================================================== */
function initTheme() {
  const savedTheme = localStorage.getItem('theme') || 'dark'; // Default to dark mode
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeButtonIcon(savedTheme);

  const toggleBtn = document.getElementById('theme-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme');
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      
      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('theme', newTheme);
      updateThemeButtonIcon(newTheme);
    });
  }
}

function updateThemeButtonIcon(theme) {
  const icon = document.getElementById('theme-icon');
  if (!icon) return;
  
  if (theme === 'dark') {
    // Show Sun icon for toggling to light mode
    icon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m12.728 12.728l.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z"/>`;
  } else {
    // Show Moon icon for toggling to dark mode
    icon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>`;
  }
}

/* ==========================================================================
   Dashboard Controller
   ========================================================================== */
function initDashboard(card) {
  const fileInput = document.getElementById('file-upload-input');
  const progressContainer = document.getElementById('upload-progress');
  const progressBar = document.getElementById('upload-progress-fill');
  const progressPercent = document.getElementById('upload-percent');
  const progressStatus = document.getElementById('upload-status-text');

  // Trigger file dialog
  card.addEventListener('click', () => fileInput.click());

  // Drag over states
  card.addEventListener('dragover', (e) => {
    e.preventDefault();
    card.classList.add('dragover');
  });

  card.addEventListener('dragleave', () => {
    card.classList.remove('dragover');
  });

  card.addEventListener('drop', (e) => {
    e.preventDefault();
    card.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      handleFilesUpload(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFilesUpload(fileInput.files);
    }
  });

  function handleFilesUpload(files) {
    const formData = new FormData();
    let hasZip = false;

    for (let i = 0; i < files.length; i++) {
      if (files[i].name.endsWith('.zip')) {
        formData.append('files', files[i]);
        hasZip = true;
      }
    }

    if (!hasZip) {
      alert('Please upload only .zip files exported by the extension.');
      return;
    }

    // Initialize progress indicators
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressPercent.textContent = '0%';
    progressStatus.textContent = 'Uploading files...';

    // Perform upload
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload', true);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = percent + '%';
        progressPercent.textContent = percent + '%';
        if (percent === 100) {
          progressStatus.textContent = 'Extracting and parsing ZIP files on server...';
        }
      }
    });

    xhr.onreadystatechange = () => {
      if (xhr.readyState === XMLHttpRequest.DONE) {
        try {
          const response = JSON.parse(xhr.responseText);
          if (xhr.status === 200 && response.success) {
            progressStatus.textContent = 'Success! Reloading dashboard...';
            progressBar.style.backgroundColor = '#10b981'; // Green success color
            setTimeout(() => {
              window.location.reload();
            }, 1000);
          } else {
            handleError(response.error || 'Upload failed');
          }
        } catch (e) {
          handleError('Server returned an invalid response');
        }
      }
    };

    xhr.onerror = () => handleError('Network error occurred during upload');

    xhr.send(formData);
  }

  function handleError(message) {
    progressStatus.textContent = 'Error: ' + message;
    progressBar.style.backgroundColor = '#ef4444'; // Red failure color
    fileInput.value = '';
  }
}

/* ==========================================================================
   Chat Viewer Controller
   ========================================================================== */
function initViewer() {
  const chatName = document.getElementById('chat-viewer-viewport').getAttribute('data-chat');
  const messagesList = document.getElementById('messages-list-timeline');
  const searchInput = document.getElementById('search-messages');
  const loader = document.getElementById('loading-indicator');
  const viewport = document.getElementById('chat-viewer-viewport');

  // Viewer State Variables
  let allMessages = [];
  let filteredMessages = [];
  let renderedCount = 0;
  const BATCH_SIZE = 500;
  let currentActiveDate = "";

  // Lightbox Elements
  const lightbox = document.getElementById('lb-viewer');
  const lightboxMedia = document.getElementById('lb-media-container');
  const lightboxClose = document.getElementById('lb-close-btn');

  // Trigger Message API Fetch
  fetchMessages();

  function fetchMessages() {
    fetch(`/api/chat/${chatName}`)
      .then(res => res.json())
      .then(res => {
        if (res.success) {
          // Enrich all messages with their global index
          allMessages = res.messages.map((msg, index) => {
            msg.global_idx = index;
            return msg;
          });
          filteredMessages = [...allMessages];
          loader.style.display = 'none';
          
          // Render initial batch
          renderNextBatch(true);
          
          // Hook scroll event for infinite lazy scroll
          viewport.addEventListener('scroll', handleViewportScroll);
          
          // Hook search input
          searchInput.addEventListener('input', debounce(handleSearchInput, 300));
        } else {
          showError(res.error || 'Failed to fetch messages');
        }
      })
      .catch(err => {
        console.error(err);
        showError('Network error loading messages.');
      });
  }

  // Infinite lazy scrolling trigger
  function handleViewportScroll() {
    // When within 300px from the bottom, load the next batch
    const triggerPosition = viewport.scrollTop + viewport.clientHeight >= viewport.scrollHeight - 300;
    if (triggerPosition) {
      renderNextBatch(false);
    }
  }

  // Lazy Render Messages Batch
  function renderNextBatch(isInitial = false) {
    const limit = Math.min(renderedCount + BATCH_SIZE, filteredMessages.length);
    renderMessagesUpTo(limit);
    
    // Proactively scroll to bottom on initial load
    if (isInitial) {
      setTimeout(() => {
        viewport.scrollTop = viewport.scrollHeight;
      }, 50);
    }
  }

  // Render Messages up to a given limit
  function renderMessagesUpTo(limit) {
    if (renderedCount >= filteredMessages.length) return;

    const start = renderedCount;
    const end = Math.min(limit, filteredMessages.length);
    const fragment = document.createDocumentFragment();
    const isSearchMode = searchInput.value.trim() !== "";

    for (let i = start; i < end; i++) {
      const msg = filteredMessages[i];

      // Add date separator if the date string changes
      if (msg.date_str !== currentActiveDate) {
        currentActiveDate = msg.date_str;
        const dateSep = document.createElement('div');
        dateSep.className = 'date-sep';
        dateSep.innerHTML = `<span>${currentActiveDate}</span>`;
        fragment.appendChild(dateSep);
      }

      // Construct individual message nodes
      const isSystemEvent = msg.bubble_html && msg.bubble_html.includes('class="unsup"');
      const msgDiv = document.createElement('div');
      msgDiv.className = `msg ${isSystemEvent ? 'system-event' : msg.direction}`;
      msgDiv.setAttribute('id', `msg-${msg.global_idx}`);
      
      let senderHtml = '';
      if (msg.sender_name && msg.direction === 'recv') {
        const hasPrevSameSender = i > 0 && 
                                filteredMessages[i-1].direction === 'recv' && 
                                filteredMessages[i-1].sender_name === msg.sender_name &&
                                filteredMessages[i-1].date_str === msg.date_str;
        
        if (!hasPrevSameSender) {
          let picHtml = '';
          if (msg.sender_pic) {
            picHtml = `<img class="sender-pic" src="${msg.sender_pic}" alt="">`;
          } else {
            const initial = msg.sender_name ? msg.sender_name[0].toUpperCase() : 'U';
            picHtml = `<div class="sender-pic sender-pic-placeholder">${initial}</div>`;
          }
          senderHtml = `<div class="sender-info">${picHtml}<span class="sender-name">${msg.sender_name}</span></div>`;
        }
      }

      let jumpBtnHtml = '';
      if (isSearchMode) {
        jumpBtnHtml = `
          <button class="msg-jump-btn" data-idx="${msg.global_idx}" title="Go to Chat Context">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width: 10px; height: 10px; margin-right: 4px; display: inline-block; vertical-align: middle;">
              <path d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5"/>
            </svg>Go to chat
          </button>
        `;
      }

      msgDiv.innerHTML = `
        ${senderHtml}
        ${msg.bubble_html}
        <div class="time-container">
          <div class="time">${msg.time_str}</div>
          ${jumpBtnHtml}
        </div>
      `;

      // Handle custom light toggle for displaying message timestamp on bubble click
      const bubble = msgDiv.querySelector('.bubble');
      const time = msgDiv.querySelector('.time');
      if (bubble && time) {
        bubble.addEventListener('click', () => {
          time.classList.toggle('visible');
        });
      }

      fragment.appendChild(msgDiv);
    }

    messagesList.appendChild(fragment);
    renderedCount = end;

    // Attach click handlers to newly added jump buttons
    const jumpBtns = messagesList.querySelectorAll('.msg-jump-btn:not(.bound)');
    jumpBtns.forEach(btn => {
      btn.classList.add('bound');
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const targetIdx = parseInt(btn.getAttribute('data-idx'));
        jumpToMessage(targetIdx);
      });
    });

    // Attach media and voice note triggers
    attachMediaTriggers();
    initVoicePlayers();
  }

  // Jump to a message in the full conversation stream
  function jumpToMessage(targetIdx) {
    searchInput.value = '';
    filteredMessages = [...allMessages];
    messagesList.innerHTML = '';
    renderedCount = 0;
    currentActiveDate = "";
    
    // Render up to targetIdx + 100
    const limit = Math.min(targetIdx + 100, allMessages.length);
    renderMessagesUpTo(limit);
    
    // Scroll to and highlight
    setTimeout(() => {
      const targetEl = document.getElementById(`msg-${targetIdx}`);
      if (targetEl) {
        targetEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
        
        const bubble = targetEl.querySelector('.bubble');
        if (bubble) {
          bubble.classList.add('highlight-flash');
          setTimeout(() => {
            bubble.classList.remove('highlight-flash');
          }, 2000);
        }
      }
    }, 100);
  }

  // Asynchronous Lightbox Trigger Attachment
  function attachMediaTriggers() {
    // Find all media items and hook click events
    const mediaItems = messagesList.querySelectorAll('.media-item:not(.lightbox-bound)');
    mediaItems.forEach(item => {
      item.classList.add('lightbox-bound');
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        
        // Extract parameters from onclick string or children if restructured
        // Usually, the onclick is: openMedia('media/media_X.jpg', 'image')
        const onclickAttr = item.getAttribute('onclick');
        if (onclickAttr) {
          const match = onclickAttr.match(/openMedia\('([^']+)','([^']+)'\)/);
          if (match) {
            openLightbox(match[1], match[2]);
            return;
          }
        }
        
        // Fallback checks
        const img = item.querySelector('img');
        if (img) {
          openLightbox(img.getAttribute('src'), 'image');
        }
      });
    });
  }

  // Premium Voice Player Controller
  function initVoicePlayers() {
    const voicePlayers = messagesList.querySelectorAll('.voice-player:not(.initialized)');
    voicePlayers.forEach(player => {
      player.classList.add('initialized');
      const btn = player.querySelector('.voice-play-btn');
      const audio = player.querySelector('audio');
      const playIcon = btn.querySelector('.play-icon');
      const pauseIcon = btn.querySelector('.pause-icon');
      const durationLabel = player.querySelector('.voice-duration');
      const progressFill = player.querySelector('.voice-progress-fill');
      const progressContainer = player.querySelector('.voice-progress-container');

      audio.addEventListener('loadedmetadata', () => {
        durationLabel.textContent = formatDuration(audio.duration);
      });

      if (audio.readyState >= 1) {
        durationLabel.textContent = formatDuration(audio.duration);
      }

      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (audio.paused) {
          document.querySelectorAll('audio').forEach(a => {
            if (a !== audio) {
              a.pause();
              const p = a.closest('.voice-player');
              if (p) {
                p.querySelector('.play-icon').style.display = 'block';
                p.querySelector('.pause-icon').style.display = 'none';
              }
            }
          });
          audio.play().then(() => {
            playIcon.style.display = 'none';
            pauseIcon.style.display = 'block';
          }).catch(err => console.error(err));
        } else {
          audio.pause();
          playIcon.style.display = 'block';
          pauseIcon.style.display = 'none';
        }
      });

      audio.addEventListener('timeupdate', () => {
        const pct = (audio.currentTime / audio.duration) * 100;
        progressFill.style.width = `${pct}%`;
        durationLabel.textContent = `${formatDuration(audio.currentTime)} / ${formatDuration(audio.duration)}`;
      });

      progressContainer.addEventListener('click', (e) => {
        e.stopPropagation();
        const rect = progressContainer.getBoundingClientRect();
        const pct = (e.clientX - rect.left) / rect.width;
        audio.currentTime = pct * audio.duration;
      });

      audio.addEventListener('ended', () => {
        playIcon.style.display = 'block';
        pauseIcon.style.display = 'none';
        progressFill.style.width = '0%';
        durationLabel.textContent = formatDuration(audio.duration);
      });
    });
  }

  function formatDuration(sec) {
    if (isNaN(sec) || !isFinite(sec)) return "0:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  }

  /* ==========================================================================
     Lightbox Handlers
     ========================================================================== */
  function openLightbox(src, type) {
    lightboxMedia.innerHTML = '';
    
    if (type === 'video') {
      lightboxMedia.innerHTML = `<video src="${src}" controls autoplay style="width:100%; height:100%;"></video>`;
    } else {
      lightboxMedia.innerHTML = `<img src="${src}" alt="Fullscreen Media">`;
    }

    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';

    // Hook close controls
    lightboxClose.onclick = closeLightbox;
    lightbox.onclick = (e) => {
      if (e.target === lightbox || e.target.classList.contains('lightbox-content')) {
        closeLightbox();
      }
    };
    document.addEventListener('keydown', handleEscClose);
  }

  function closeLightbox() {
    const video = lightboxMedia.querySelector('video');
    if (video) video.pause();
    
    lightbox.classList.remove('active');
    document.body.style.overflow = '';
    document.removeEventListener('keydown', handleEscClose);
  }

  function handleEscClose(e) {
    if (e.key === 'Escape') closeLightbox();
  }

  /* ==========================================================================
     Real-time Local Filtering (Text Search)
     ========================================================================== */
  function handleSearchInput() {
    const query = searchInput.value.toLowerCase().trim();
    messagesList.innerHTML = '';
    renderedCount = 0;
    currentActiveDate = "";

    if (!query) {
      filteredMessages = [...allMessages];
    } else {
      filteredMessages = allMessages.filter(msg => {
        // Strip tags from HTML to perform plain-text searching
        const textContent = msg.bubble_html.replace(/<[^>]*>/g, '').toLowerCase();
        const sender = (msg.sender_name || '').toLowerCase();
        return textContent.includes(query) || sender.includes(query);
      });
    }

    // Render filtered batch
    renderNextBatch(false);
  }

  function showError(msg) {
    loader.style.display = 'none';
    messagesList.innerHTML = `
      <div style="text-align:center; padding: 40px; border: 1px solid var(--border-color); border-radius: 12px; background-color: var(--bg-primary);">
        <p style="color:#ef4444; font-weight:600; margin-bottom:8px;">Failed to load chat timeline</p>
        <p style="color:var(--text-muted); font-size:13px;">${msg}</p>
      </div>
    `;
  }
}

// Simple debounce helper
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}
