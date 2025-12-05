document.addEventListener('DOMContentLoaded', () => {
    // 页面加载时自动滚动到.add-artwork-container顶部
    const container = document.querySelector('.add-artwork-container');
    if (container) {
        container.scrollIntoView({ behavior: 'auto', block: 'start' });
    }
    const form = document.getElementById('add-artwork-form');
    const urlDropZone = document.getElementById('url-drop-zone'); // 新增
    const fileDropZone = document.getElementById('file-drop-zone'); // 新增
    const fileInput = document.getElementById('artwork_file');
    const imagePreview = document.getElementById('image-preview');
    const titleInput = document.getElementById('title');
    const platformInput = document.getElementById('platform');
    const artistInput = document.getElementById('artist');
    const submitButton = document.getElementById('submit-button');
    const formStatus = document.getElementById('form-status');
    const artworkUrlInput = document.getElementById('artwork_url');
    const galleryDlProxyInput = document.getElementById('gallery_dl_proxy');
    const fetchButton = document.getElementById('fetch-button');
    const fetchStatus = document.getElementById('fetch-status');
    const hiddenTempInput = document.getElementById('temp_filename_input');
    const checkDuplicateBtn = document.getElementById('check-duplicate-btn');
    const resetFormBtn = document.getElementById('reset-form-btn');
    const ratingStars = document.querySelectorAll('.rating-star');
    const ratingInput = document.getElementById('rating');

    let tempFilenameFromServer = null; // 用于存储从URL下载的临时文件名

    // --- Star Rating Logic ---
    ratingStars.forEach(star => {
        star.addEventListener('click', () => {
            const ratingValue = star.value;
            
            // Update stars UI
            ratingStars.forEach((s, index) => {
                if (index < ratingValue) {
                    s.textContent = '★';
                    s.classList.add('rated');
                } else {
                    s.textContent = '☆';
                    s.classList.remove('rated');
                }
            });
            
            // Set the hidden input value
            ratingInput.value = ratingValue;
        });
    });

    // Add reset button functionality
    const resetRatingButton = document.querySelector('.rating-reset');
    if (resetRatingButton) {
        resetRatingButton.addEventListener('click', () => {
            resetRating();
        });
    }

    // 重置评分函数
    function resetRating() {
        // Reset stars UI
        ratingStars.forEach(star => {
            star.textContent = '☆';
            star.classList.remove('rated');
        });
        
        // Clear the hidden input value
        ratingInput.value = '';
    }

    // --- URL Fetch Logic ---
    if (fetchButton) {
        fetchButton.addEventListener('click', async () => {
            const url = artworkUrlInput.value.trim();
            if (!url) {
                fetchStatus.textContent = 'Please enter a valid URL.';
                return;
            }

            fetchStatus.innerHTML = '<span class="loading-spinner"></span> Fetching metadata...';
            fetchButton.disabled = true;

            try {
                const proxy = galleryDlProxyInput.value.trim() || null;
                const response = await fetch('/api/fetch_metadata', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url, proxy })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    const data = result.data;
                    platformInput.value = data.platform || '';
                    artistInput.value = data.artist || '';
                    titleInput.value = data.title || '';

                    if (data.classification) {
                        document.getElementById('classification').value = data.classification;
                    }

                    // 填充publication_date、tags和description字段
                    if (data.publication_date) {
                        document.getElementById('publication_date').value = data.publication_date;
                    }
                    if (data.tags) {
                        document.getElementById('tags').value = data.tags;
                    }
                    if (data.description) {
                        document.getElementById('description').value = data.description;
                    }

                    // 核心: 将临时文件名存入隐藏输入框，并清空文件输入
                    hiddenTempInput.value = result.temp_path;
                    fileInput.value = ''; // 清空手动选择的文件
                    imagePreview.src = `/temp_image/${result.temp_path}`;
                    imagePreview.classList.remove('hidden');
                    // 隐藏文件拖放区的提示文本
                    const p = fileDropZone.querySelector('p');
                    if (p) p.style.display = 'none'; // 直接设置display为none
                    fileInput.required = false;

                    // 显示图片位置信息
                    let statusMessage = 'Metadata fetched successfully!';
                    if (result.image_info) {
                        const info = result.image_info;
                        if (info.is_multi_image_post) {
                            statusMessage += ` (Image ${info.current_image_position} of ${info.total_images_in_post})`;
                        } else if (info.total_images_in_post > 1) {
                            statusMessage += ` (Part of multi-image post, total: ${info.total_images_in_post})`;
                        }
                    }
                    fetchStatus.textContent = statusMessage;
                    
                    // 检查是否需要自动查找重复
                    const autoCheckDuplicate = document.getElementById('auto-check-duplicate');
                    if (autoCheckDuplicate && autoCheckDuplicate.checked) {
                        // 延迟执行重复检查，确保页面元素已更新
                        setTimeout(() => {
                            checkForDuplicates();
                        }, 500);
                    }
                    
                    // 平滑滚动到表单操作按钮区域
                    // 使用setTimeout确保页面布局更新后再进行滚动定位
                    setTimeout(() => {
                        const formActions = document.querySelector('.form-actions');
                        if (formActions) {
                            const rect = formActions.getBoundingClientRect();
                            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                            // 调整滚动位置，使按钮位于屏幕下方10px处
                            const targetTop = rect.top + scrollTop - window.innerHeight + formActions.offsetHeight + 20;
                            window.scrollTo({
                                top: targetTop,
                                behavior: 'smooth'
                            });
                        }
                    }, 200);
                } else {
                    fetchStatus.textContent = result.error || 'Failed to fetch metadata.';
                }
            } catch (error) {
                fetchStatus.textContent = 'An error occurred while fetching metadata.';
            } finally {
                fetchButton.disabled = false;
            }
        });
    }

    // --- Drag & Drop Logic ---
    // 文件拖放区点击事件
    fileDropZone.addEventListener('click', () => fileInput.click());

    // 文件拖放区拖拽事件
    fileDropZone.addEventListener('dragover', (e) => { e.preventDefault(); fileDropZone.classList.add('dragover'); });
    fileDropZone.addEventListener('dragleave', () => fileDropZone.classList.remove('dragover'));
    fileDropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        fileDropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect(fileInput.files[0]);
        }
    });

    // URL 拖放区拖拽事件
    urlDropZone.addEventListener('dragover', (e) => { e.preventDefault(); urlDropZone.classList.add('dragover'); });
    urlDropZone.addEventListener('dragleave', () => urlDropZone.classList.remove('dragover'));
    urlDropZone.addEventListener('drop', async (e) => {
        e.preventDefault();
        urlDropZone.classList.remove('dragover');

        const draggedUrl = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
        if (draggedUrl && (draggedUrl.startsWith('http://') || draggedUrl.startsWith('https://'))) {
            artworkUrlInput.value = draggedUrl;
            fetchButton.click(); // 自动触发fetch
        }
    });

    fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFileSelect(fileInput.files[0]); });

    function handleFileSelect(file) {
        if (file && file.type && file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                imagePreview.src = e.target.result;
                imagePreview.classList.remove('hidden');
                // 隐藏文件拖放区的提示文本
                const p = fileDropZone.querySelector('p');
                if (p) p.style.display = 'none'; // 直接设置display为none
            };
            reader.readAsDataURL(file);

            // 核心: 清空隐藏输入框，确保我们处于“手动上传”模式
            hiddenTempInput.value = '';
            fileInput.required = true;
            
            // 设置文件输入框的值，确保表单提交时包含文件
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files;

            // 清空URL输入框和状态
            artworkUrlInput.value = '';
            fetchStatus.textContent = '';
            
            // 清空评分
            resetRating();
            
            // 检查是否需要自动查找重复
            const autoCheckDuplicate = document.getElementById('auto-check-duplicate');
            if (autoCheckDuplicate && autoCheckDuplicate.checked) {
                // 延迟执行重复检查，确保页面元素已更新
                setTimeout(() => {
                    checkForDuplicates();
                }, 500);
            }
        }
    }

    // --- Autocomplete Logic ---
    /*
     Replace the existing setupAutocomplete function with the following implementation.
     It performs a two-stage filter:
      1) items that startWith the user's input (case-insensitive)
      2) items that include the user's input but don't start with it
     Results preserve original casing when displayed/filled.
    */
    function setupAutocomplete(inputElement, apiUrl) {
        let allItemsLower = [];           // 小写版用于匹配
        let originalItems = [];           // 原始版用于显示
        const resultsContainer = inputElement.parentElement.querySelector('.autocomplete-results');

        // 获取候选项并建立映射
        fetch(apiUrl)
            .then(res => res.json())
            .then(data => {
                originalItems = Array.isArray(data) ? data : [];
                allItemsLower = originalItems.map(item => item.toLowerCase());
            })
            .catch(() => {
                originalItems = [];
                allItemsLower = [];
            });

        inputElement.addEventListener('input', () => {
            const value = inputElement.value.trim().toLowerCase();
            resultsContainer.innerHTML = '';
            if (!value) {
                resultsContainer.style.display = 'none';
                return;
            }
            resultsContainer.style.display = 'block';

            const startsWithMatches = [];
            const includesMatches = [];

            // 两轮筛选（在一次循环中完成以避免重复）
            for (let i = 0; i < allItemsLower.length; i++) {
                const lower = allItemsLower[i];
                if (lower.startsWith(value)) {
                    startsWithMatches.push(i); // 存索引，便于取原始大小写
                } else if (lower.includes(value)) {
                    includesMatches.push(i);
                }
            }

            // 合并索引，优先 startsWith，然后 includes
            const mergedIndexes = startsWithMatches.concat(includesMatches).slice(0, 5);

            mergedIndexes.forEach(idx => {
                const original = originalItems[idx];
                const div = document.createElement('div');
                div.textContent = original;
                div.addEventListener('click', () => {
                    inputElement.value = original; // 填充原始大小写
                    resultsContainer.innerHTML = '';
                });
                resultsContainer.appendChild(div);
            });
        });

        // 点击页面其他地方时关闭结果面板
        document.addEventListener('click', (e) => {
            if (e.target !== inputElement) {
                resultsContainer.innerHTML = '';
            }
        });
    }
    setupAutocomplete(platformInput, '/api/platforms');
    setupAutocomplete(artistInput, '/api/artists');

    // --- Reset Form Logic ---
    function resetForm() {
        form.reset();
        imagePreview.classList.add('hidden');
        const p = fileDropZone.querySelector('p');
        if (p) p.style.display = 'block'; // 重新显示文件拖放区的提示文本
        hiddenTempInput.value = '';
        fileInput.required = true;
        artworkUrlInput.value = '';
        galleryDlProxyInput.value = '';
        fetchStatus.textContent = '';
        formStatus.textContent = '';
        formStatus.className = '';

        // 重置按钮状态
        submitButton.disabled = false;
        submitButton.textContent = 'Upload Artwork';
        checkDuplicateBtn.disabled = false;
        checkDuplicateBtn.textContent = 'Check for Duplicates';

        // 重置评分
        resetRating();
    }

    // --- Check Duplicate Logic ---
    async function checkForDuplicates() {
        if (!fileInput.files.length && !hiddenTempInput.value) {
            alert('Please select an image file first.');
            return;
        }

        checkDuplicateBtn.disabled = true;
        checkDuplicateBtn.textContent = 'Checking...';
        formStatus.textContent = '';
        formStatus.className = '';

        try {
            const formData = new FormData();
            
            if (hiddenTempInput.value) {
                // 如果有临时文件，从服务器获取文件内容
                const response = await fetch(`/temp_image/${hiddenTempInput.value}`);
                if (!response.ok) throw new Error('Failed to get temporary file');
                
                const blob = await response.blob();
                formData.append('search_file', blob, 'temp_image.jpg');
            } else {
                // 使用用户选择的文件
                formData.append('search_file', fileInput.files[0]);
            }

            const response = await fetch('/api/get_similar_ids', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.success) {
                if (result.ids && result.ids.length > 0) {
                    // 有重复图片，跳转到主页并显示结果
                    const searchParams = new URLSearchParams({ similar_to: result.ids });
                    window.location.href = `/?${searchParams.toString()}`;
                } else {
                    formStatus.textContent = 'No duplicate images found.';
                    formStatus.classList.add('success');
                }
            } else {
                formStatus.textContent = `Error: ${result.error || 'Check failed.'}`;
                formStatus.classList.add('error');
            }
        } catch (error) {
            formStatus.textContent = 'A network error occurred while checking for duplicates.';
            formStatus.classList.add('error');
        } finally {
            checkDuplicateBtn.disabled = false;
            checkDuplicateBtn.textContent = 'Check for Duplicates';
        }
    }

    // --- Event Listeners ---
    if (resetFormBtn) {
        resetFormBtn.addEventListener('click', resetForm);
    }

    if (checkDuplicateBtn) {
        checkDuplicateBtn.addEventListener('click', checkForDuplicates);
    }

    // --- Form Submission Logic ---
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        submitButton.disabled = true;
        submitButton.textContent = 'Uploading...';
        formStatus.textContent = '';
        formStatus.className = '';

        // 核心: 使用 new FormData(form)，它现在能自动包含隐藏输入框或文件输入
        const formData = new FormData(form);
        
        // 确保在拖拽上传时手动将文件数据添加到FormData中
        if (fileInput.files.length > 0 && !hiddenTempInput.value) {
            formData.set('artwork_file', fileInput.files[0]);
        }
        
        try {
            const response = await fetch(form.action, { method: 'POST', body: formData });
            const result = await response.json();

            if (response.ok) {
                formStatus.textContent = result.message;
                formStatus.classList.add('success');
                
                // 立即重置表单
                resetForm();
                
                // 重置评分
                resetRating();
                
                // 平滑滚动到页面初始位置
                const container = document.querySelector('.add-artwork-container');
                if (container) {
                    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            } else {
                formStatus.textContent = `Error: ${result.error}`;
                formStatus.classList.add('error');
            }
        } catch (error) {
            formStatus.textContent = 'A network error occurred.';
            formStatus.classList.add('error');
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = 'Upload Artwork';
        }
    });
});
