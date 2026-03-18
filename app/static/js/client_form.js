document.addEventListener('DOMContentLoaded', function() {
    const nameInput = document.getElementById('name');
    const symbolInput = document.getElementById('symbol');

    // Auto-format Client Name to Title Case
    if (nameInput) {
        nameInput.addEventListener('blur', function() {
            let val = this.value;
            // Basic Title Case: Capitalize first letter of each word
            // Using regex to match first letter of string or first letter after whitespace
            val = val.toLowerCase().replace(/(?:^|\s)\S/g, function(a) { 
                return a.toUpperCase(); 
            });
            this.value = val;
        });
    }

    // Auto-format Symbol to Uppercase
    if (symbolInput) {
        symbolInput.addEventListener('input', function() {
            this.value = this.value.toUpperCase();
        });
    }
});
