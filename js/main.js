// 화면 연출: 스크롤하면 하나씩 나타나기, 헤더 배경, 첫 화면 조명
(function () {
    // 1) 화면에 들어온 요소를 천천히 떠오르게 한다
    var items = document.querySelectorAll(".reveal");
    if ("IntersectionObserver" in window) {
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-in");
                    io.unobserve(entry.target);     // 한 번 나타나면 더 볼 필요 없다
                }
            });
        }, { rootMargin: "0px 0px -6% 0px", threshold: 0.1 });
        items.forEach(function (el) { io.observe(el); });
    } else {
        items.forEach(function (el) { el.classList.add("is-in"); });
    }

    // 2) 조금이라도 내려가면 헤더 배경을 진하게 깐다
    var header = document.querySelector(".site-header");
    function onScroll() {
        header.classList.toggle("scrolled", window.scrollY > 24);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    // 3) 첫 화면에서는 마우스를 따라 은은한 조명이 움직인다 (마우스가 있는 기기만)
    var hero = document.querySelector(".hero");
    if (hero && window.matchMedia("(pointer: fine)").matches) {
        hero.addEventListener("mousemove", function (e) {
            var r = hero.getBoundingClientRect();
            hero.style.setProperty("--mx", (e.clientX - r.left) + "px");
            hero.style.setProperty("--my", (e.clientY - r.top) + "px");
        });
    }
})();
