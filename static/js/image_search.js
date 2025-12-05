document.addEventListener('DOMContentLoaded', () => {
    // 获取模态框元素
    const modal = document.getElementById('image-search-modal');
    const trigger = document.getElementById('image-search-trigger');
    const closeBtn = document.querySelector('.modal .close');
    const dropZone = document.getElementById('image-drop-zone');
    const fileInput = document.getElementById('file-input');
    const imagePreview = document.getElementById('image-preview');
    const thresholdSlider = document.getElementById('threshold-slider');
    const thresholdValue = document.getElementById('threshold-value');
    const searchButton = document.getElementById('search-button');
    const searchStatus = document.getElementById('search-status');
    
    // 显示模态框
    if (trigger) {
        trigger.addEventListener('click', () => {
            modal.style.display = 'block';
        });
    }
    
    // 关闭模态框
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
            resetModal();
        });
    }
    
    // 点击模态框外部关闭
    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
            resetModal();
        }
    });
    
    // 拖拽事件处理
    if (dropZone) {
        dropZone.addEventListener('click', () => fileInput.click());
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            
            if (e.dataTransfer.files.length) {
                handleFile(e.dataTransfer.files[0]);
            }
        });
        
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) {
                handleFile(fileInput.files[0]);
            }
        });
    }
    
    // 阈值滑块事件处理
    if (thresholdSlider && thresholdValue) {
        thresholdSlider.addEventListener('input', () => {
            thresholdValue.textContent = thresholdSlider.value;
        });
    }
    
    // 搜索按钮事件处理
    if (searchButton) {
        searchButton.addEventListener('click', performSearch);
    }
    
    // 用于存储拖拽的文件
    let droppedFile = null;
    
    // 处理文件选择
    function handleFile(file) {
        if (file && file.type && file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                imagePreview.src = e.target.result;
                imagePreview.classList.remove('hidden');
                dropZone.querySelector('p').style.display = 'none';
            };
            reader.readAsDataURL(file);
            searchStatus.textContent = '';
            searchStatus.className = 'search-status';
            
            // 保存拖拽的文件
            droppedFile = file;
        }
    }
    
    // 执行搜索
    async function performSearch() {
        // 检查是否有拖拽的文件或选择的文件
        if (!droppedFile && !fileInput.files.length) {
            searchStatus.textContent = 'Please select an image file first.';
            searchStatus.className = 'search-status error';
            return;
        }
        
        searchButton.disabled = true;
        searchButton.textContent = 'Searching...';
        searchStatus.textContent = '';
        searchStatus.className = 'search-status';
        
        try {
            const formData = new FormData();
            // 使用拖拽的文件或选择的文件
            if (droppedFile) {
                formData.append('search_file', droppedFile);
            } else {
                formData.append('search_file', fileInput.files[0]);
            }
            formData.append('threshold', thresholdSlider.value);
            
            const response = await fetch('/api/get_similar_ids', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                if (result.ids && result.ids.length > 0) {
                    // 有相似图片，跳转到主页并显示结果
                    const searchParams = new URLSearchParams({ 
                        similar_to: result.ids,
                        threshold: thresholdSlider.value
                    });
                    window.location.href = `/?${searchParams.toString()}`;
                } else {
                    searchStatus.textContent = 'No similar images found.';
                    searchStatus.className = 'search-status success';
                }
            } else {
                searchStatus.textContent = `Error: ${result.error || 'Search failed.'}`;
                searchStatus.className = 'search-status error';
            }
        } catch (error) {
            searchStatus.textContent = 'A network error occurred while searching.';
            searchStatus.className = 'search-status error';
        } finally {
            searchButton.disabled = false;
            searchButton.textContent = 'Search';
        }
    }
    
    // 重置模态框
    function resetModal() {
        if (fileInput) fileInput.value = '';
        if (imagePreview) {
            imagePreview.classList.add('hidden');
            imagePreview.src = '#';
        }
        if (dropZone) {
            const p = dropZone.querySelector('p');
            if (p) p.style.display = 'block';
        }
        if (thresholdSlider) thresholdSlider.value = '10';
        if (thresholdValue) thresholdValue.textContent = '10';
        if (searchStatus) {
            searchStatus.textContent = '';
            searchStatus.className = 'search-status';
        }
        if (searchButton) {
            searchButton.disabled = false;
            searchButton.textContent = 'Search';
        }
        // 重置拖拽的文件
        droppedFile = null;
    }
});