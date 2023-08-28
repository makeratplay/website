var app = angular.module("app", ['ngSanitize']);

app.controller('AppController', function($http, $scope, $sce) {
    var vm = this;
    vm.selectedProject = {};
    vm.data = [];
    vm.categories = [];
    vm.category = '';
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
                vm.categories = extractUniqueCategories(vm.data);
            });
    }

    function extractUniqueCategories(inputArray) {
      const uniqueCategories = new Set();
    
      for (const obj of inputArray) {
        if (obj.hasOwnProperty('category')) {
          for( const text of obj.category){
            uniqueCategories.add(text);
          }
        }
      }
      return Array.from(uniqueCategories).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));;
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

    vm.setCategory = function( selecedItem )
    {
      if ( vm.category == selecedItem)
      {
        vm.category = ''
      }
      else
      {
        vm.category = selecedItem;
      }
    }

    $scope.trustSrc = function(src) {
      return $sce.trustAsResourceUrl(src);
    }
    
    $scope.movie = {src:"http://www.youtube.com/embed/Lx7ycjC8qjE", title:"Egghead.io AngularJS Binding"};

    $scope.selectedCategory = ''; // Default selected category

    // Custom filter function
    $scope.categoryFilter = function(item) {
      if (vm.category === '' ){
        return true;
      }
      else if ( item.category.includes(vm.category) ) {
        return true;
      }
      return false;
    };

});

