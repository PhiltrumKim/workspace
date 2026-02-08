

//var test = "()()(()(())((())(())";
//var test = "(()))";
//var test = "(())())";
//var test = "(())";
//var test = ")()("; 
//var test = "(()))()(";
var test = "((()()))())";


var ret = solution(test);

console.log(ret);

function solution(s)
{
    var answer = true;

    // 문자열의 길이가 100,000 이하의 자연수
    if(s.length > 100000)
    {
        return false;
    }   
    
    // 시작이 '(' 이고 끝이 ')' 가 아닐 경우 Error
    if(s[0] != '(' || s[s.length - 1] != ')')
    {
        return false;
    }

    // 문자열의 괄호가 ()로 이루어져 있는지 확인
    var count = 0;  
    for(var i = 0; i < s.length; i++)
    {        
        
        if(s[i] == '(')
        {
            count++;
        }
        else if(s[i] == ')')
        {
            count--;
        }
        else
        {
            // '(' 또는 ')' 가 아닌 문자가 있을 경우 Error
            return false;
        }
    }

    if(count != 0)
    {
        // 괄호의 갯수가 맞지 않을 경우 Error
        answer = false;
    }   

    console.log(`Count -> ${count}` );

    return answer;

}