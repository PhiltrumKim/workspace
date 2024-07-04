var ret = solution("(())())");

console.log(ret);

function solution(s)
{
    var answer = true;

    // 문자열의 길이가 100,000 이하의 자연수
    if(s.length > 100000)
    {
        return false;
    }      

    // 문자열 s는 '(' 또는 ')' 
    for(var i = 0; i < s.length; i++)
    {
        if(s[i] == '(' || s[i] == ')')
        {
            continue;
        }
        else
        {
            return false;
        }
    }

    // 문자열의 괄호가 ()로 이루어져 있는지 확인
    var count = 0;  
    for(var i = 0; i < s.length; i++)
    {
        if(i == 0 && s[i] != '(')
        {
            return false;
        }
        
        if(s[i] == '(')
        {
            count++;
        }
        else if(s[i] == ')')
        {
            count--;
        }
    }

    if(count != 0)
    {
        return false;
    }   


    return answer;

}