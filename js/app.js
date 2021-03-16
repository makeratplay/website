var app = angular.module("app", ['ngSanitize']);

app.controller('AppController', function($http, $scope, $sce) {
    var vm = this;
    vm.selectedProject = {};
    vm.data = [];
    vm.affiliateData = [[],[],[],[]];
    init();


    function init() {
        getData();
        getAffiliateData();
    }

    function getData() {
        return $http.get("/data.json").then(
            function(response) {
                vm.data = response.data;
            });
    }

    function getAffiliateData() {
      return $http.get("/affiliate_links.json").then(
          function(response) {
            //break file into 4 columns
            let length = response.data.length
            for ( let i = 0; i < length; i++ )
            {
              vm.affiliateData[i%4].push(response.data[i]);
            }
              
          });
  }    


    vm.viewProject = function(project){
      vm.selectedProject = project;
      if ( project.hasOwnProperty('page') ){
        window.open(project.page,"_self")
      }
      else{
        $('#projectModal').modal('show');
      }
    }

    $scope.trustSrc = function(src) {
      return $sce.trustAsResourceUrl(src);
    }
    
    $scope.movie = {src:"http://www.youtube.com/embed/Lx7ycjC8qjE", title:"Egghead.io AngularJS Binding"};


});