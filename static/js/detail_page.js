// static/js/detail_page.js (重构版 - 新的编辑模式)
document.addEventListener('DOMContentLoaded', () => {
    // 为HTML元素添加js-enabled类，用于CSS控制非JS设备的元素显示
    document.documentElement.classList.add('js-enabled');
    
    // 显示查找相似按钮，因为默认在HTML中是隐藏的
    const findSimilarBtn = document.getElementById('find-similar-btn');
    if (findSimilarBtn) {
        findSimilarBtn.style.display = 'inline-block';
    }
    
    const deleteBtn = document.getElementById('delete-artwork-btn');
    const editFieldsBtn = document.getElementById('edit-fields-btn');
    const saveFieldsBtn = document.getElementById('save-fields-btn');
    const cancelEditBtn = document.getElementById('cancel-edit-btn');

    // --- 查找相似 ---
    if (findSimilarBtn) {
        findSimilarBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            const artworkId = findSimilarBtn.dataset.artworkId;
            const threshold = 10;
            
            findSimilarBtn.textContent = 'Finding...';
            findSimilarBtn.style.pointerEvents = 'none';

            try {
                const response = await fetch(`/api/get_similar_ids_by_id/${artworkId}?threshold=${threshold}`);
                const result = await response.json();

                if (response.ok && result.success) {
                    if (result.ids && result.ids.length > 0) {
                        const searchParams = new URLSearchParams({ similar_to: result.ids, threshold: threshold });
                        window.location.href = `/?${searchParams.toString()}`;
                    } else {
                        alert('No similar images found.');
                    }
                } else {
                    alert(`Error: ${result.error || 'Search failed.'}`);
                }
            } catch (error) {
                console.error('Find similar fetch error:', error);
                alert('A network error occurred.');
            } finally {
                findSimilarBtn.textContent = 'Find Similar';
                findSimilarBtn.style.pointerEvents = 'auto';
            }
        });
    }
    
    // --- 删除 ---
    if (deleteBtn) {
        deleteBtn.addEventListener('click', async () => {
            const artworkId = deleteBtn.dataset.artworkId;
            if (confirm('Are you sure you want to move this artwork to the trash? This action cannot be undone from the web interface.')) {
                try {
                    deleteBtn.textContent = 'Deleting...';
                    deleteBtn.disabled = true;

                    const response = await fetch(`/api/delete_artwork/${artworkId}`, {
                        method: 'POST'
                    });
                    const result = await response.json();
                    
                    if (response.ok && result.success) {
                        // 只弹出一次确认菜单，并自动回到浏览器的上个页面
                        window.history.back();
                    } else {
                        alert(`Error: ${result.error}`);
                        deleteBtn.textContent = 'Delete';
                        deleteBtn.disabled = false;
                    }
                } catch (error) {
                    alert('A network error occurred.');
                    deleteBtn.textContent = 'Delete';
                    deleteBtn.disabled = false;
                }
            }
        });
    }

    // --- 新的编辑模式逻辑 ---
    const artworkId = document.querySelector('.detail-actions')?.querySelector('[data-artwork-id]')?.dataset.artworkId;
    if (!artworkId) return;

    let originalValues = {};
    let isEditMode = false;

    // 编辑按钮点击事件
    if (editFieldsBtn) {
        editFieldsBtn.addEventListener('click', () => {
            enterEditMode();
        });
    }

    // 保存按钮点击事件
    if (saveFieldsBtn) {
        saveFieldsBtn.addEventListener('click', () => {
            saveChanges();
        });
    }

    // 取消按钮点击事件
    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', () => {
            cancelEdit();
        });
    }

    // 进入编辑模式
    function enterEditMode() {
        if (isEditMode) return;
        
        isEditMode = true;
        originalValues = {};
        
        // 显示/隐藏按钮
        editFieldsBtn.style.display = 'none';
        saveFieldsBtn.style.display = 'inline-block';
        cancelEditBtn.style.display = 'inline-block';
        
        // 转换所有可编辑字段为输入框
        document.querySelectorAll('.editable-field').forEach(field => {
            const fieldName = field.dataset.field;
            const currentValue = field.textContent.trim();
            // 保存原始的 outerHTML，以便在取消编辑时恢复
            originalValues[fieldName] = {
                text: currentValue,
                html: field.outerHTML
            };
            
            if (field.classList.contains('multiline')) {
                // 多行文本转换为textarea
                const textarea = document.createElement('textarea');
                textarea.value = currentValue;
                textarea.rows = 4;
                textarea.className = 'edit-textarea';
                textarea.dataset.field = fieldName;
                field.replaceWith(textarea);
            } else if (field.classList.contains('artwork-title')) {
                // 标题转换为input，保持大字号
                const input = document.createElement('input');
                input.type = 'text';
                input.value = currentValue;
                input.className = 'edit-input artwork-title';
                input.dataset.field = fieldName;
                field.replaceWith(input);
            } else {
                // 单行文本转换为input
                const input = document.createElement('input');
                input.type = 'text';
                input.value = currentValue;
                input.className = 'edit-input';
                input.dataset.field = fieldName;
                field.replaceWith(input);
            }
        });
    }

    // 保存更改
    async function saveChanges() {
        if (!isEditMode) return;
        
        const updates = {};
        let hasChanges = false;
        
        // 收集所有更改
        document.querySelectorAll('.edit-input, .edit-textarea').forEach(input => {
            const fieldName = input.dataset.field;
            if (fieldName) {
                const newValue = input.value.trim();
                const originalValue = originalValues[fieldName];
                
                if (newValue !== originalValue) {
                    updates[fieldName] = newValue;
                    hasChanges = true;
                }
            }
        });
        
        if (!hasChanges) {
            exitEditMode();
            return;
        }
        
        // 保存按钮状态
        saveFieldsBtn.textContent = 'Saving...';
        saveFieldsBtn.disabled = true;
        
        try {
            // 逐个更新字段
            for (const [fieldName, newValue] of Object.entries(updates)) {
                const response = await fetch(`/api/update_artwork_field/${artworkId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ field: fieldName, value: newValue })
                });
                
                if (!response.ok) {
                    const result = await response.json();
                    throw new Error(result.error || 'Update failed');
                }
            }
            
            // 更新成功，刷新页面显示新数据
            window.location.reload();
            
        } catch (error) {
            alert(`Error saving changes: ${error.message}`);
            saveFieldsBtn.textContent = 'Save Changes';
            saveFieldsBtn.disabled = false;
        }
    }

    // 取消编辑
    function cancelEdit() {
        if (!isEditMode) return;
        
        // 恢复原始值
        document.querySelectorAll('.edit-input, .edit-textarea').forEach(input => {
            const fieldName = input.dataset.field;
            const originalValue = originalValues[fieldName];
            
            // 创建新的元素来替换input/textarea
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = originalValue.html;
            const newElement = tempDiv.firstElementChild;
            
            // 替换input/textarea为原始元素
            input.replaceWith(newElement);
        });
        
        // 恢复按钮状态
        exitEditMode();
    }

    // 退出编辑模式
    function exitEditMode() {
        isEditMode = false;
        originalValues = {};
        
        editFieldsBtn.style.display = 'inline-block';
        saveFieldsBtn.style.display = 'none';
        cancelEditBtn.style.display = 'none';
    }
    
    // --- 无刷新评级 ---
    const ratingForms = document.querySelectorAll('.rating-form');

    ratingForms.forEach(form => {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const url = form.action;
            const clickedButton = event.submitter;
            if (!clickedButton) return;

            const ratingValue = clickedButton.value;
            const formData = new FormData();
            formData.append('rating', ratingValue);

            try {
                // 发送 AJAX 请求
                const response = await fetch(url, {
                    method: 'POST',
                    body: new URLSearchParams(formData),
                    // 添加这个头，让后端知道这是一个 AJAX 请求
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });

                if (response.ok) {
                    // 解析后端返回的JSON数据
                    const data = await response.json();
                    const finalRating = data.new_rating; // 可能是数字，也可能是 null

                    const stars = form.querySelectorAll('button');
                    
                    // --- 核心UI更新逻辑 ---
                    stars.forEach(star => {
                        const starValue = parseInt(star.value);
                        // 如果有最终评分，且星星的值小于等于它
                        if (finalRating && starValue <= finalRating) {
                            star.textContent = '★'; // 实心
                            star.classList.add('rated');
                        } else {
                            star.textContent = '☆'; // 空心
                            star.classList.remove('rated');
                        }
                    });

                    // 更新详情页的文字
                    const currentRatingSpan = form.querySelector('.current-rating') || form.closest('.detail-info')?.querySelector('.current-rating');
                    if (currentRatingSpan) {
                        currentRatingSpan.textContent = `(Current: ${finalRating || 'Unrated'}/10)`;
                    }
                } else {
                    console.error('Rating update failed:', response.statusText);
                }
            } catch (error) {
                console.error('An error occurred during fetch:', error);
            }
        });
    });
    
    // --- 无刷新分类更改 ---
    const classificationForms = document.querySelectorAll('.classification-form');
    classificationForms.forEach(form => {
        const select = form.querySelector('select[name="classification"]');
        const updateButton = form.querySelector('button[type="submit"]');
        
        // 对于有JS的用户, 隐藏 "Update" 按钮
        if (updateButton) {
            updateButton.style.display = 'none';
        }
        
        // 为 select 添加 'change' 事件监听器
        if (select) {
            select.addEventListener('change', async () => {
                const url = form.action;
                const formData = new FormData();
                formData.append('classification', select.value);

                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        body: new URLSearchParams(formData),
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });

                    if (!response.ok) {
                        console.error('Classification update failed:', response.statusText);
                    }
                    // 成功后无需做任何UI更新, 因为select本身已经处于正确的选中状态
                } catch (error) {
                    console.error('An error occurred during fetch:', error);
                }
            });
        }
    });
    
    // --- 无刷新类别更改 ---
    const categoryForms = document.querySelectorAll('.category-form');
    categoryForms.forEach(form => {
        const select = form.querySelector('select[name="category"]');
        const updateButton = form.querySelector('button[type="submit"]');
        
        // 对于有JS的用户, 隐藏 "Update" 按钮
        if (updateButton) {
            updateButton.style.display = 'none';
        }
        
        // 为 select 添加 'change' 事件监听器
        if (select) {
            select.addEventListener('change', async () => {
                const url = form.action;
                const formData = new FormData();
                formData.append('category', select.value);

                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        body: new URLSearchParams(formData),
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });

                    if (!response.ok) {
                        console.error('Category update failed:', response.statusText);
                    }
                    // 成功后无需做任何UI更新, 因为select本身已经处于正确的选中状态
                } catch (error) {
                    console.error('An error occurred during fetch:', error);
                }
            });
        }
    });
});
