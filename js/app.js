var app = angular.module("app", ['ngSanitize']);

app.controller('AppController', function($http, $scope, $sce) {
    var vm = this;
    vm.selectedProject = {};
    vm.data = [];
    init();


    function init() {
        getData();
    }

    function getData() {
        return $http.get("/data.json").then(
            function(response) {
                vm.data = response.data;
            });
    }


    vm.viewProject = function(project){
      vm.selectedProject = project;

      $('#projectModal').modal('show');
    }

    $scope.trustSrc = function(src) {
      return $sce.trustAsResourceUrl(src);
    }
    
    $scope.movie = {src:"http://www.youtube.com/embed/Lx7ycjC8qjE", title:"Egghead.io AngularJS Binding"};


});