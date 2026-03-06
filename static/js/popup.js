/**
 * First Visit Popup - Cookie Management and UI Control
 * 
 * This module handles the first-visit popup functionality including:
 * - Cookie management for tracking user visits
 * - Content loading from backend API
 * - Language and content type switching
 * - UI interaction handling
 */

// ============================================================================
// Cookie Management Functions
// ============================================================================

/**
 * Get a cookie value by name
 * @param {string} name - The name of the cookie to retrieve
 * @returns {string|null} The cookie value or null if not found
 */
function getCookie(name) {
  try {
    const nameEQ = name + "=";
    const cookies = document.cookie.split(';');
    
    for (let i = 0; i < cookies.length; i++) {
      let cookie = cookies[i];
      // Trim leading spaces
      while (cookie.charAt(0) === ' ') {
        cookie = cookie.substring(1);
      }
      // Check if this cookie matches the name we're looking for
      if (cookie.indexOf(nameEQ) === 0) {
        return cookie.substring(nameEQ.length);
      }
    }
    return null;
  } catch (e) {
    console.error('Error reading cookie:', e);
    return null;
  }
}

/**
 * Set a cookie with name, value, and expiration days
 * @param {string} name - The name of the cookie
 * @param {string} value - The value to store
 * @param {number} days - Number of days until expiration
 */
function setCookie(name, value, days) {
  try {
    const date = new Date();
    date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
    const expires = "expires=" + date.toUTCString();
    // Set cookie with path=/public as per requirements
    document.cookie = name + "=" + value + ";" + expires + ";path=/public;SameSite=Lax";
  } catch (e) {
    console.error('Error setting cookie:', e);
  }
}

/**
 * Check if this is the user's first visit
 * @returns {boolean} True if first visit, false otherwise
 */
function checkFirstVisit() {
  try {
    const visited = getCookie('visited_before');
    return visited === null || visited !== 'true';
  } catch (e) {
    console.error('Error checking first visit:', e);
    // Default to showing popup if there's an error
    return true;
  }
}

/**
 * Mark the user as having visited
 * Sets the visited_before cookie with 365 days expiration
 */
function markAsVisited() {
  try {
    setCookie('visited_before', 'true', 365);
  } catch (e) {
    console.warn('Failed to mark as visited (cookie operation failed):', e);
    // Don't throw - allow popup to close even if cookie fails
  }
}

// ============================================================================
// Content Loading Functions
// ============================================================================

/**
 * Load popup content from the backend API
 * @param {string} type - Content type: 'declaration' or 'terms'
 * @param {string} lang - Language code: 'zh' or 'en'
 * @returns {Promise<Object>} Promise resolving to response data with structure:
 *   { success: boolean, content?: string, error?: string, type: string, lang: string }
 */
async function loadPopupContent(type, lang) {
  try {
    // Construct API URL with query parameters
    const url = `/public/api/popup_content?type=${encodeURIComponent(type)}&lang=${encodeURIComponent(lang)}`;
    
    // Make fetch request to backend API
    const response = await fetch(url);
    
    // Check if HTTP response is OK
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    // Parse JSON response
    const data = await response.json();
    
    return data;
  } catch (e) {
    // Handle network errors, server errors, or JSON parsing errors
    console.error('Failed to load popup content:', e);
    
    // Return error response in the same format as successful response
    return {
      success: false,
      error: lang === 'zh' ? '内容加载失败，请稍后再试' : 'Failed to load content, please try again later',
      type: type,
      lang: lang
    };
  }
}

// ============================================================================
// UI Control Functions
// ============================================================================

/**
 * Show the popup and overlay
 * Validates: Requirements 5.1, 5.2
 */
function showPopup() {
  try {
    const popup = document.getElementById('first-visit-popup');
    if (popup) {
      popup.style.display = 'flex';
    } else {
      console.error('Popup element not found');
    }
  } catch (e) {
    console.error('Error showing popup:', e);
  }
}

/**
 * Hide the popup and mark user as visited
 * Validates: Requirements 5.2, 5.6
 */
function hidePopup() {
  try {
    const popup = document.getElementById('first-visit-popup');
    if (popup) {
      popup.style.display = 'none';
    }
    // Mark user as visited by setting cookie
    markAsVisited();
  } catch (e) {
    console.error('Error hiding popup:', e);
  }
}

/**
 * Update popup content and title based on loaded data
 * @param {Object} data - Response data from loadPopupContent
 *   { success: boolean, content?: string, error?: string, type: string, lang: string }
 * Validates: Requirements 5.1, 5.2
 */
function updatePopupContent(data) {
  try {
    const contentArea = document.getElementById('popup-content-area');
    const titleElement = document.getElementById('popup-title');
    
    if (!contentArea || !titleElement) {
      console.error('Popup content elements not found');
      return;
    }
    
    if (data.success && data.content) {
      // Update content with HTML from backend
      contentArea.innerHTML = data.content;
      
      // Update title based on content type and language
      const titles = {
        declaration: {
          zh: '网站声明',
          en: 'Website Declaration'
        },
        terms: {
          zh: '使用须知',
          en: 'Terms of Use'
        }
      };
      
      titleElement.textContent = titles[data.type]?.[data.lang] || '内容';
    } else {
      // Display error message
      const errorMsg = data.error || (data.lang === 'zh' ? '内容加载失败' : 'Failed to load content');
      contentArea.innerHTML = `<div class="popup-error">${errorMsg}</div>`;
    }
  } catch (e) {
    console.error('Error updating popup content:', e);
    // Display generic error message
    const contentArea = document.getElementById('popup-content-area');
    if (contentArea) {
      contentArea.innerHTML = '<div class="popup-error">内容更新失败 / Content update failed</div>';
    }
  }
}

/**
 * Update button labels based on current state
 * @param {Object} state - Current state object with type and lang properties
 *   { type: 'declaration' | 'terms', lang: 'zh' | 'en' }
 * Validates: Requirements 5.6
 */
function updateButtonLabels(state) {
  try {
    const contentBtn = document.getElementById('popup-switch-content');
    const langBtn = document.getElementById('popup-switch-lang');
    
    if (!contentBtn || !langBtn) {
      console.error('Button elements not found');
      return;
    }
    
    // Update content switch button label
    // Show the target content type (what user will see after clicking)
    const contentLabels = {
      declaration: {
        zh: '查看使用须知',
        en: 'View Terms of Use'
      },
      terms: {
        zh: '查看网站声明',
        en: 'View Declaration'
      }
    };
    
    contentBtn.textContent = contentLabels[state.type]?.[state.lang] || '切换内容';
    
    // Update language switch button label
    // Show the target language (what user will see after clicking)
    const langLabels = {
      zh: 'Switch to English',
      en: '切换到中文'
    };
    
    langBtn.textContent = langLabels[state.lang] || 'Switch Language';
  } catch (e) {
    console.error('Error updating button labels:', e);
  }
}

// ============================================================================
// State Management and Switching Logic
// ============================================================================

/**
 * Current state of the popup
 * Tracks the current content type and language
 * Validates: Requirements 3.1, 4.1
 */
let currentState = {
  type: 'declaration',  // 'declaration' or 'terms'
  lang: 'zh'            // 'zh' or 'en'
};

/**
 * Switch to the other language and reload content
 * Maintains the current content type while changing language
 * Validates: Requirements 3.2, 3.4, 3.5
 */
async function switchLanguage() {
  try {
    // Toggle language: zh <-> en
    currentState.lang = currentState.lang === 'zh' ? 'en' : 'zh';
    
    // Load content with new language but same content type
    const data = await loadPopupContent(currentState.type, currentState.lang);
    
    // Update UI with new content
    updatePopupContent(data);
    updateButtonLabels(currentState);
  } catch (e) {
    console.error('Error switching language:', e);
    // Revert language on error
    currentState.lang = currentState.lang === 'zh' ? 'en' : 'zh';
  }
}

/**
 * Switch to the other content type and reload content
 * Maintains the current language while changing content type
 * Validates: Requirements 4.2, 4.4, 4.5
 */
async function switchContent() {
  try {
    // Toggle content type: declaration <-> terms
    currentState.type = currentState.type === 'declaration' ? 'terms' : 'declaration';
    
    // Load content with new type but same language
    const data = await loadPopupContent(currentState.type, currentState.lang);
    
    // Update UI with new content
    updatePopupContent(data);
    updateButtonLabels(currentState);
  } catch (e) {
    console.error('Error switching content:', e);
    // Revert content type on error
    currentState.type = currentState.type === 'declaration' ? 'terms' : 'declaration';
  }
}

// ============================================================================
// Initialization and Event Binding
// ============================================================================

/**
 * Initialize the popup system on page load
 * Validates: Requirements 1.2, 3.1, 4.1, 5.1, 5.2, 5.6
 */
document.addEventListener('DOMContentLoaded', async function() {
  try {
    // Check if this is the user's first visit
    if (checkFirstVisit()) {
      // Load default content (Chinese declaration)
      const data = await loadPopupContent('declaration', 'zh');
      
      // Update popup with loaded content
      updatePopupContent(data);
      updateButtonLabels(currentState);
      
      // Show the popup
      showPopup();
    }
    
    // Bind event listeners regardless of whether popup is shown
    // (in case user manually triggers popup or for future visits)
    bindEventListeners();
  } catch (e) {
    console.error('Error initializing popup:', e);
  }
});

/**
 * Bind all event listeners for popup interactions
 * Validates: Requirements 5.2, 5.6, 3.1, 4.1
 */
function bindEventListeners() {
  try {
    // Get all interactive elements
    const closeBtn = document.getElementById('popup-close');
    const overlay = document.getElementById('first-visit-popup');
    const switchContentBtn = document.getElementById('popup-switch-content');
    const switchLangBtn = document.getElementById('popup-switch-lang');
    
    // Bind close button click event
    if (closeBtn) {
      closeBtn.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent event bubbling
        hidePopup();
      });
    } else {
      console.warn('Close button not found');
    }
    
    // Bind overlay click event (clicking outside popup closes it)
    if (overlay) {
      overlay.addEventListener('click', function(e) {
        // Only close if clicking directly on overlay, not on popup content
        if (e.target === overlay) {
          hidePopup();
        }
      });
    } else {
      console.warn('Popup overlay not found');
    }
    
    // Bind language switch button click event
    if (switchLangBtn) {
      switchLangBtn.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent event bubbling
        switchLanguage();
      });
    } else {
      console.warn('Language switch button not found');
    }
    
    // Bind content switch button click event
    if (switchContentBtn) {
      switchContentBtn.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent event bubbling
        switchContent();
      });
    } else {
      console.warn('Content switch button not found');
    }
  } catch (e) {
    console.error('Error binding event listeners:', e);
  }
}
