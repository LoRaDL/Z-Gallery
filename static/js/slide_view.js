// static/js/slide_view.js
document.addEventListener('DOMContentLoaded', () => {
    // 为HTML元素添加js-enabled类，用于CSS控制非JS设备的元素显示
    document.documentElement.classList.add('js-enabled');

    // 获取DOM元素
    const prevButton = document.getElementById('prev-button');
    const nextButton = document.getElementById('next-button');
    const imageElement = document.getElementById('slide-image');
    const imageContainer = document.getElementById('image-container');
    const ratingForms = document.querySelectorAll('.rating-form');

    // 从页面URL获取当前艺术品ID和过滤器参数
    const urlParams = new URLSearchParams(window.location.search);
    const currentId = urlParams.get('id');

    // 使用HTML锚点定位，JS定位代码已移除

    // 图片切换函数
    async function navigateToImage(direction) {
        // 获取当前URL参数
        const urlParams = new URLSearchParams(window.location.search);
        const currentFilters = {};
        
        // 收集所有过滤参数
        for (const [key, value] of urlParams.entries()) {
            if (key !== 'id') {
                currentFilters[key] = value;
            }
        }

        try {
            // 请求获取下一张或上一张图片的ID
            const response = await fetch(`/api/get_${direction}_image`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'  // 添加这个头，让后端知道这是一个 AJAX 请求
                },
                body: JSON.stringify({ 
                    current_id: currentId, 
                    filters: currentFilters 
                })
            });

            const result = await response.json();
            
            if (response.ok && result.success && result.artwork_id) {
                // 构建新的URL
                const newParams = new URLSearchParams(currentFilters);
                newParams.set('id', result.artwork_id);
                
                // 直接跳转到新图片，并带上锚点
                window.location.href = `?${newParams.toString()}#image-top`;
            } else {
                // 如果没有更多图片，显示提示
                alert(`No ${direction === 'next' ? 'next' : 'previous'} images available.`);
            }
        } catch (error) {
            console.error('Navigation error:', error);
            alert('Failed to load image. Please try again.');
        }
    }

    // 添加按钮点击事件
    if (prevButton) {
        prevButton.addEventListener('click', (event) => {
            // 阻止默认行为，仅在JS启用时使用AJAX导航
            event.preventDefault();
            navigateToImage('previous');
        });
    }

    if (nextButton) {
        nextButton.addEventListener('click', (event) => {
            // 阻止默认行为，仅在JS启用时使用AJAX导航
            event.preventDefault();
            navigateToImage('next');
        });
    }

    // 键盘导航
    document.addEventListener('keydown', (e) => {
        // 左右箭头键导航
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            navigateToImage('previous');
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            navigateToImage('next');
        }
    });

    // 无刷新评分，并在评分后自动跳转到下一张图片
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
                    // 评分成功后自动切换到下一张图片
                    navigateToImage('next');
                } else {
                    console.error('Rating update failed:', response.statusText);
                }
            } catch (error) {
                console.error('An error occurred during fetch:', error);
            }
        });
    });

    // 移除拖放导航支持，防止点击屏幕切换图片
    // 为有JS支持的设备添加拖放导航支持
    // if (imageElement) {
    //     let startX = 0;
    //     let endX = 0;

    //     // 鼠标/触摸事件
    //     imageElement.addEventListener('mousedown', handleStart);
    //     imageElement.addEventListener('touchstart', handleStart, { passive: true });
    //     
    //     document.addEventListener('mousemove', handleMove);
    //     document.addEventListener('touchmove', handleMove, { passive: true });
    //     
    //     document.addEventListener('mouseup', handleEnd);
    //     document.addEventListener('touchend', handleEnd, { passive: true });

    //     function handleStart(e) {
    //         startX = e.type.includes('mouse') ? e.clientX : e.touches[0].clientX;
    //     }

    //     function handleMove(e) {
    //         endX = e.type.includes('mouse') ? e.clientX : e.touches[0].clientX;
    //     }

    //     function handleEnd() {
    //         // 如果移动距离超过30像素，则导航到上一张或下一张
    //         const diff = startX - endX;
    //         if (Math.abs(diff) > 30) {
    //             if (diff > 0) {
    //                 navigateToImage('next'); // 向左滑动
    //             } else {
    //                 navigateToImage('previous'); // 向右滑动
    //             }
    //         }
    //     }
    // }
});