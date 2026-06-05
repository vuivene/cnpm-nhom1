document.addEventListener("DOMContentLoaded", function() {
    // Lấy đường dẫn URL hiện tại của trình duyệt (ví dụ: /nhan-vien)
    const currentUrl = window.location.pathname;
    
    // Tìm tất cả các thẻ liên kết trong menu sidebar
    const menuLinks = document.querySelectorAll(".sidebar-menu li a");
    
    menuLinks.forEach(link => {
        const linkHref = link.getAttribute("href");
        
        // Logic so sánh thông minh để bật class active
        if (currentUrl === linkHref || (linkHref !== '/bang-quan-tri' && linkHref !== '/' && currentUrl.startsWith(linkHref))) {
            link.classList.add("active");
        } else {
            link.classList.remove("active");
        }
    });
});