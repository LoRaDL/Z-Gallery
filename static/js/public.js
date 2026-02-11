// Public Mode Specific JavaScript

document.addEventListener('DOMContentLoaded', () => {
    console.log('Public mode JavaScript loaded');
    
    // Public mode specific functionality
    // Disable any interactive features that should not work in public mode
    
    // Disable rating form submissions in public mode
    const ratingForms = document.querySelectorAll('.rating-form form, .rating-form-detail form');
    ratingForms.forEach(form => {
        form.addEventListener('submit', (event) => {
            event.preventDefault();
            console.log('Rating submission disabled in public mode');
            return false;
        });
        
        // Disable all buttons in rating forms
        const buttons = form.querySelectorAll('button');
        buttons.forEach(button => {
            button.disabled = true;
            button.style.cursor = 'default';
        });
    });
    
    // Disable classification forms in public mode
    const classificationForms = document.querySelectorAll('.classification-form');
    classificationForms.forEach(form => {
        form.addEventListener('submit', (event) => {
            event.preventDefault();
            console.log('Classification update disabled in public mode');
            return false;
        });
        
        const radioButtons = form.querySelectorAll('input[type="radio"]');
        radioButtons.forEach(radio => {
            radio.disabled = true;
        });
    });
    
    // Disable category forms in public mode
    const categoryForms = document.querySelectorAll('.category-form');
    categoryForms.forEach(form => {
        form.addEventListener('submit', (event) => {
            event.preventDefault();
            console.log('Category update disabled in public mode');
            return false;
        });
        
        const radioButtons = form.querySelectorAll('input[type="radio"]');
        radioButtons.forEach(radio => {
            radio.disabled = true;
        });
        
        const selectElements = form.querySelectorAll('select');
        selectElements.forEach(select => {
            select.disabled = true;
        });
    });
    
    // Remove any delete buttons or edit links
    const deleteButtons = document.querySelectorAll('.delete-button, [data-action="delete"]');
    deleteButtons.forEach(button => {
        button.remove();
    });
    
    const editButtons = document.querySelectorAll('.edit-button, [data-action="edit"]');
    editButtons.forEach(button => {
        button.remove();
    });
});
