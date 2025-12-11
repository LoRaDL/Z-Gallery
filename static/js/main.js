// 公共的评分处理函数
window.setupRatingHandler = function(form) {
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const url = form.action;
        const clickedButton = event.submitter;
        if (!clickedButton) return;

        const ratingValue = parseInt(clickedButton.value);
        const formData = new FormData();
        formData.append('rating', ratingValue);

        const stars = form.querySelectorAll('button');
        
        // 触觉反馈 - iPhone震动
        if ('vibrate' in navigator) {
            // 标准震动API（Android和部分设备）
            navigator.vibrate(10); // 10ms轻微震动
        }
        if (window.navigator && window.navigator.vibrate) {
            // 备用方案
            window.navigator.vibrate(10);
        }
        // iOS Haptic Feedback（需要用户交互触发）
        try {
            if (window.Taptic && window.Taptic.impact) {
                window.Taptic.impact('light');
            }
        } catch (e) {
            // Taptic不可用，忽略
        }
        
        // 立即显示"pending"状态 - 半亮的星
        stars.forEach(star => {
            const starValue = parseInt(star.value);
            star.classList.remove('rated', 'pending');
            
            if (starValue <= ratingValue) {
                star.textContent = '★'; // 实心
                star.classList.add('pending'); // 添加pending类
            } else {
                star.textContent = '☆'; // 空心
            }
        });

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

                // --- 核心UI更新逻辑 - 移除pending，添加最终状态 ---
                stars.forEach(star => {
                    const starValue = parseInt(star.value);
                    star.classList.remove('pending');
                    
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
                // 请求失败，恢复原状态
                console.error('Rating update failed:', response.statusText);
                stars.forEach(star => {
                    star.classList.remove('pending');
                    star.textContent = '☆';
                    star.classList.remove('rated');
                });
            }
        } catch (error) {
            // 网络错误，恢复原状态
            console.error('An error occurred during fetch:', error);
            stars.forEach(star => {
                star.classList.remove('pending');
                star.textContent = '☆';
                star.classList.remove('rated');
            });
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    // 为HTML元素添加js-enabled类，用于CSS控制非JS设备的元素显示
    document.documentElement.classList.add('js-enabled');
    
    // --- 逻辑1: 无刷新评级 (代码无变化) ---
    const ratingForms = document.querySelectorAll('.rating-form form, .rating-form-detail form');

    ratingForms.forEach(form => {
        setupRatingHandler(form);
    });

    // --- 逻辑2: 新增的无刷新分级 ---
    const classificationForm = document.querySelector('.classification-form');
    if (classificationForm) {
        const updateButton = classificationForm.querySelector('button[type="submit"]');
        const radioButtons = classificationForm.querySelectorAll('input[type="radio"]');

        // 对于有JS的用户, 隐藏 "Update" 按钮
        if (updateButton) {
            updateButton.style.display = 'none';
        }

        // 为每个单选按钮添加 'change' 事件监听器
        radioButtons.forEach(radio => {
            radio.addEventListener('change', async () => {
                const form = radio.closest('form');
                const url = form.action;
                const formData = new FormData();
                formData.append('classification', radio.value);

                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        body: new URLSearchParams(formData),
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });

                    if (!response.ok) {
                        console.error('Classification update failed:', response.statusText);
                    }
                    // 成功后无需做任何UI更新, 因为单选按钮本身已经处于正确的选中状态
                } catch (error) {
                    console.error('An error occurred during fetch:', error);
                }
            });
        });
    }

    // --- 逻辑3: 新增的无刷新分类更改 ---
    // 只处理在gallery页面上的category表单（使用radio按钮的），不处理detail页面的category表单（使用select的）
    const categoryForm = document.querySelector('.gallery .category-form');
    if (categoryForm) {
        const updateButton = categoryForm.querySelector('button[type="submit"]');
        const radioButtons = categoryForm.querySelectorAll('input[type="radio"]');

        // 对于有JS的用户, 隐藏 "Update" 按钮
        if (updateButton) {
            updateButton.style.display = 'none';
        }

        // 为每个单选按钮添加 'change' 事件监听器
        radioButtons.forEach(radio => {
            radio.addEventListener('change', async () => {
                const form = radio.closest('form');
                const url = form.action;
                const formData = new FormData();
                formData.append('category', radio.value);

                try {
                    const response = await fetch(url, {
                        method: 'POST',
                        body: new URLSearchParams(formData),
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });

                    if (!response.ok) {
                        console.error('Category update failed:', response.statusText);
                    }
                } catch (error) {
                    console.error('An error occurred during fetch:', error);
                }
            });
        });
    }

    // --- 逻辑4: (渐进增强) 为支持JS的浏览器给图片添加链接 ---
    const galleryCards = document.querySelectorAll('.card');

    galleryCards.forEach(card => {
        const image = card.querySelector('img');
        const titleLink = card.querySelector('.title a'); // 找到标题中的链接

        // 如果卡片里同时有图片和标题链接
        if (image && titleLink) {
            // 获取标题链接的URL
            const detailUrl = titleLink.href;

            // 创建一个新的 <a> 标签来包裹图片
            const imageLinkWrapper = document.createElement('a');
            imageLinkWrapper.href = detailUrl;

            // --- "包裹"操作 ---
            // 1. 在DOM中，将新的 <a> 标签插入到图片的前面
            image.parentNode.insertBefore(imageLinkWrapper, image);
            // 2. 将图片移动到新的 <a> 标签内部，成为其子元素
            imageLinkWrapper.appendChild(image);
        }
    });

    // --- 逻辑5: (渐进增强) 为支持JS的浏览器重新启用图片链接 ---
    // 找到所有被CSS默认禁用的图片链接
    const disabledImageLinks = document.querySelectorAll('.card-image-link');

    disabledImageLinks.forEach(link => {
        // 使用JS将它们的点击功能恢复
        link.style.pointerEvents = 'auto';
    });
});