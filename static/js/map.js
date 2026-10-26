// 지도 검색: 입력한 말을 구글 지도 주소에 넣어 지도를 바꾼다 (API 키가 필요 없는 방식)
(function () {
    var form = document.getElementById("map-form");
    var input = document.getElementById("map-input");
    var frame = document.getElementById("map-frame");
    var current = document.getElementById("map-current");
    var naver = document.getElementById("naver-map");
    var google = document.getElementById("google-map");

    var HOME = "뮤직포스";

    function moveMap(place, label) {
        frame.src = "https://www.google.com/maps?q=" + encodeURIComponent(place) + "&z=15&hl=ko&output=embed";
        naver.href = "https://map.naver.com/v5/search/" + encodeURIComponent(place);
        google.href = "https://www.google.com/maps/search/" + encodeURIComponent(place);
        current.textContent = label;
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();                 // 페이지가 새로고침되지 않게 막는다
        var place = input.value.trim();
        if (place !== "") {
            moveMap(place, place);
        }
    });

    document.getElementById("map-reset").addEventListener("click", function () {
        input.value = "";
        moveMap(HOME, "뮤직포스 (전시 협조 매장)");
    });
})();
